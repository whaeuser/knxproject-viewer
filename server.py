import asyncio
import json
import logging
import os
import tempfile
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Set

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from xknx import XKNX
from xknx.io import ConnectionConfig, ConnectionType
from xknxproject import XKNXProj
from xknxproject.exceptions import InvalidPasswordException, XknxProjectException

INDEX_HTML = Path(__file__).parent / "index.html"
CONFIG_PATH = Path(__file__).parent / "config.json"
ANNOTATIONS_PATH = Path(__file__).parent / "annotations.json"
LOG_PATH = Path(__file__).parent / "logs" / "knx_bus.log"
LAST_PROJECT_PATH = Path(__file__).parent / "last_project.json"

state: dict = {
    "xknx": None,
    "connected": False,
    "gateway_ip": "",
    "gateway_port": 3671,
    "language": "de-DE",
    "project_data": None,
    "ga_dpt_map": {},
    "current_values": {},
    "telegram_buffer": deque(maxlen=500),
    "ws_clients": set(),
    "connect_task": None,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"gateway_ip": "", "gateway_port": 3671, "language": "de-DE"}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def setup_log():
    LOG_PATH.parent.mkdir(exist_ok=True)
    handler = TimedRotatingFileHandler(
        LOG_PATH, when="midnight", backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("knx_bus")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


bus_logger = setup_log()


async def broadcast(msg: dict):
    dead = set()
    for ws in state["ws_clients"]:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    state["ws_clients"] -= dead


def telegram_received_cb(telegram):
    asyncio.create_task(_process_telegram(telegram))


async def _process_telegram(telegram):
    src = str(telegram.source_address)
    ga = str(telegram.destination_address)

    device_name = ""
    if state["project_data"]:
        dev = state["project_data"].get("devices", {}).get(src, {})
        device_name = dev.get("name", "")

    ga_name = ""
    if state["project_data"]:
        for gad in state["project_data"].get("group_addresses", {}).values():
            if gad.get("address") == ga:
                ga_name = gad.get("name", "")
                break

    # Raw value (payload before DPT decoding)
    if hasattr(telegram.payload, "value") and telegram.payload.value is not None:
        raw_value = str(telegram.payload.value)
    else:
        raw_value = str(telegram.payload)

    # Use xknx's decoded value (DPT-aware) if available, otherwise fall back to raw
    if telegram.decoded_data is not None:
        decoded = telegram.decoded_data.value
        unit = getattr(telegram.decoded_data.transcoder, "unit", "") or ""
        if isinstance(decoded, bool):
            value = "Ein" if decoded else "Aus"
        elif isinstance(decoded, float):
            value = f"{decoded:.2f}{' ' + unit if unit else ''}"
        else:
            value = f"{decoded}{' ' + unit if unit else ''}"
    else:
        value = raw_value

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    entry = {
        "type": "telegram",
        "ts": ts,
        "src": src,
        "device": device_name,
        "ga": ga,
        "ga_name": ga_name,
        "value": value,
        "raw": raw_value,
    }

    bus_logger.info(f"{ts} | {src} | {device_name} | {ga} | {ga_name} | {value}")

    state["current_values"][ga] = {"value": value, "ts": ts}
    state["telegram_buffer"].append(entry)

    await broadcast(entry)


async def knx_connect_loop():
    cfg = load_config()
    ip = cfg.get("gateway_ip", "")
    port = cfg.get("gateway_port", 3671)
    state["gateway_ip"] = ip
    state["gateway_port"] = port
    state["language"] = cfg.get("language", "de-DE")

    if not ip:
        return

    retry_delay = 10
    while True:
        xknx = XKNX(
            connection_config=ConnectionConfig(
                connection_type=ConnectionType.TUNNELING,
                gateway_ip=ip,
                gateway_port=port,
            )
        )
        state["xknx"] = xknx
        if state["ga_dpt_map"]:
            xknx.group_address_dpt.set(state["ga_dpt_map"])
        try:
            async with xknx:
                xknx.telegram_queue.register_telegram_received_cb(telegram_received_cb)
                state["connected"] = True
                retry_delay = 10  # reset on success
                await broadcast({"type": "status", "connected": True, "ip": ip, "port": port})
                await asyncio.Event().wait()  # block until cancelled or exception
        except asyncio.CancelledError:
            break  # task was cancelled (e.g. new gateway config) — stop retrying
        except Exception as e:
            logging.getLogger("knx_bus").warning(
                "KNX connection lost: %s — retry in %ds", e, retry_delay
            )
            await broadcast({"type": "status", "connected": False, "error": str(e)})
            retry_delay = min(retry_delay * 2, 60)  # exponential backoff, max 60s
        finally:
            state["connected"] = False
            state["xknx"] = None

        try:
            await asyncio.sleep(retry_delay)
        except asyncio.CancelledError:
            break


def load_log_into_buffer():
    """Pre-populate telegram_buffer and current_values from the persisted log file."""
    if not LOG_PATH.exists():
        return
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-500:]:
            parts = line.strip().split(" | ")
            if len(parts) == 6:
                ts, src, device, ga, ga_name, value = parts
                entry = {
                    "type": "telegram",
                    "ts": ts, "src": src, "device": device,
                    "ga": ga, "ga_name": ga_name, "value": value,
                }
                state["telegram_buffer"].append(entry)
                # last seen value per GA
                state["current_values"][ga] = {"value": value, "ts": ts}
    except Exception as e:
        logging.getLogger("knx_bus").error("Error loading log: %s", e)


async def start_connect_task():
    if state["connect_task"] and not state["connect_task"].done():
        state["connect_task"].cancel()
        try:
            await state["connect_task"]
        except asyncio.CancelledError:
            pass
    state["connect_task"] = asyncio.create_task(knx_connect_loop())


def load_last_project():
    """Load last parsed project from disk into state on startup."""
    if not LAST_PROJECT_PATH.exists():
        return
    try:
        data = json.loads(LAST_PROJECT_PATH.read_text())
        state["project_data"] = data
        state["ga_dpt_map"] = {
            gad["address"]: gad.get("dpt")
            for gad in data.get("group_addresses", {}).values()
            if gad.get("address")
        }
    except Exception as e:
        logging.getLogger("knx_bus").error("Error loading last project: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_log_into_buffer()
    load_last_project()
    await start_connect_task()
    yield
    if state["connect_task"] and not state["connect_task"].done():
        state["connect_task"].cancel()
    if state["xknx"]:
        await state["xknx"].stop()


app = FastAPI(title="KNX Project Viewer", lifespan=lifespan)


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools():
    return {}


@app.get("/api/mode")
def get_mode():
    return {"public": False}


@app.get("/")
async def root():
    return FileResponse(INDEX_HTML)


@app.get("/api/gateway")
def get_gateway():
    return {
        "ip": state["gateway_ip"],
        "port": state["gateway_port"],
        "connected": state["connected"],
        "language": state["language"],
    }


@app.post("/api/gateway")
async def set_gateway(data: dict):
    save_config({
        "gateway_ip": data["ip"],
        "gateway_port": data.get("port", 3671),
        "language": data.get("language", "de-DE"),
    })
    state["language"] = data.get("language", "de-DE")
    await start_connect_task()
    return {"ok": True}


@app.get("/api/current-values")
def get_current_values():
    return state["current_values"]


@app.get("/api/last-project/info")
def get_last_project_info():
    filename = load_config().get("last_project_filename", "")
    if not filename or not LAST_PROJECT_PATH.exists():
        raise HTTPException(status_code=404, detail="No last project")
    return {"filename": filename}


@app.get("/api/last-project/data")
def get_last_project_data():
    if not state["project_data"]:
        raise HTTPException(status_code=404, detail="No project data")
    return JSONResponse(content=state["project_data"])


@app.get("/api/annotations")
def get_annotations():
    if ANNOTATIONS_PATH.exists():
        return json.loads(ANNOTATIONS_PATH.read_text())
    return {"devices": {}, "group_addresses": {}}


@app.post("/api/annotations")
async def save_annotations(data: dict):
    ANNOTATIONS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return {"ok": True}


@app.get("/api/log")
def get_log(lines: int = 500):
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            raw = f.readlines()
        entries = []
        for line in raw[-lines:]:
            parts = line.strip().split(" | ")
            if len(parts) == 6:
                ts, src, device, ga, ga_name, value = parts
                entries.append({
                    "type": "telegram",
                    "ts": ts, "src": src, "device": device,
                    "ga": ga, "ga_name": ga_name, "value": value,
                })
        return entries
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    state["ws_clients"].add(ws)
    await ws.send_json({
        "type": "status",
        "connected": state["connected"],
        "ip": state["gateway_ip"],
        "port": state["gateway_port"],
        "language": state["language"],
    })
    await ws.send_json({"type": "snapshot", "values": state["current_values"]})
    await ws.send_json({
        "type": "history",
        "entries": list(reversed(list(state["telegram_buffer"]))),  # newest first
    })
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        state["ws_clients"].discard(ws)


@app.post("/api/parse")
async def parse_project(
    file: UploadFile = File(...),
    password: str = Form(default=""),
    language: str = Form(default=""),
):
    suffix = Path(file.filename or "project.knxproj").suffix or ".knxproj"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        kwargs: dict = {"path": tmp_path}
        if password:
            kwargs["password"] = password
        if language:
            kwargs["language"] = language

        project = XKNXProj(**kwargs).parse()

        state["project_data"] = project
        state["ga_dpt_map"] = {
            gad["address"]: gad.get("dpt")
            for gad in project.get("group_addresses", {}).values()
            if gad.get("address")
        }
        # Register DPT map with the live xknx instance so future telegrams are decoded
        if state["xknx"]:
            state["xknx"].group_address_dpt.set(state["ga_dpt_map"])

        # Persist parsed project and filename for next startup
        LAST_PROJECT_PATH.write_text(json.dumps(project))
        cfg = load_config()
        cfg["last_project_filename"] = file.filename or "project.knxproj"
        save_config(cfg)

        return JSONResponse(content=project)
    except InvalidPasswordException as exc:
        raise HTTPException(status_code=422, detail=f"Invalid password: {exc}") from exc
    except XknxProjectException as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        os.unlink(tmp_path)
