import asyncio
import csv
import io
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

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from xknx import XKNX
from xknx.dpt import DPTBase
from xknx.io import ConnectionConfig, ConnectionType
from xknx.telegram import Telegram
from xknx.telegram.address import GroupAddress
from xknx.telegram.apci import GroupValueRead, GroupValueWrite
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
    dpt = ""
    if telegram.decoded_data is not None:
        decoded = telegram.decoded_data.value
        transcoder = telegram.decoded_data.transcoder
        unit = getattr(transcoder, "unit", "") or ""
        main = getattr(transcoder, "dpt_main_number", None)
        sub = getattr(transcoder, "dpt_sub_number", None)
        if main is not None:
            dpt = f"{main}.{str(sub).zfill(3)}" if sub is not None else str(main)
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
        "dpt": dpt,
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


app = FastAPI(title="Open-KNXViewer", lifespan=lifespan)


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


@app.get("/api/log/export.csv")
def export_log_csv():
    """Export complete log (all rotated files) as CSV download."""
    log_files = sorted(LOG_PATH.parent.glob("knx_bus.log*"))
    if not log_files:
        raise HTTPException(status_code=404, detail="No log files found")

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Zeitstempel", "Quell-PA", "Gerät", "GA", "GA-Name", "Wert"])
        yield buf.getvalue()
        for log_file in log_files:
            try:
                with open(log_file, encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split(" | ")
                        if len(parts) == 6:
                            buf = io.StringIO()
                            csv.writer(buf).writerow(parts)
                            yield buf.getvalue()
            except Exception:
                continue

    filename = f"knx_bus_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


# ── GA Write / Read ───────────────────────────────────────────────────────────

def _build_write_payload(dpt_info: dict, value_str: str):
    """Encode a user-supplied string value to a GroupValueWrite payload."""
    transcoder = DPTBase.parse_transcoder(dpt_info)
    if transcoder is None:
        raise ValueError(f"Unbekannter DPT: {dpt_info}")
    main = dpt_info.get("main")
    if main == 1:
        value = value_str.strip().lower() in ("1", "true", "ein", "an", "on", "yes")
    else:
        value = float(value_str)
    return GroupValueWrite(transcoder.to_knx(value))


@app.post("/api/ga/write")
async def ga_write(data: dict):
    ga_str = data.get("ga", "")
    value_str = str(data.get("value", ""))
    if not state["connected"] or state["xknx"] is None:
        raise HTTPException(status_code=503, detail="Kein KNX-Gateway verbunden")
    dpt_info = state["ga_dpt_map"].get(ga_str)
    if not dpt_info:
        raise HTTPException(status_code=422, detail="DPT für diese GA nicht bekannt")
    try:
        payload = _build_write_payload(dpt_info, value_str)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Wert konnte nicht kodiert werden: {exc}") from exc
    telegram = Telegram(destination_address=GroupAddress(ga_str), payload=payload)
    await state["xknx"].telegrams.put(telegram)
    return {"ok": True}


@app.post("/api/ga/read")
async def ga_read(data: dict):
    ga_str = data.get("ga", "")
    if not state["connected"] or state["xknx"] is None:
        raise HTTPException(status_code=503, detail="Kein KNX-Gateway verbunden")
    telegram = Telegram(destination_address=GroupAddress(ga_str), payload=GroupValueRead())
    await state["xknx"].telegrams.put(telegram)
    return {"ok": True}


# ── LLM config & analysis ─────────────────────────────────────────────────────

LLM_DEFAULT_MODEL = "z-ai/glm-5"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _build_project_summary(project_data: dict) -> str:
    """Build a compact text summary of a KNX project for LLM context."""
    lines = []
    info = project_data.get("info", {})
    lines.append(f"KNX-Projekt: {info.get('name', 'Unbekannt')}")
    lines.append(f"ETS-Version: {info.get('tool_version', '-')}")

    lines.append("\n## Topologie")
    for area_id, area in project_data.get("topology", {}).items():
        lines.append(f"  Bereich {area_id}: {area.get('name', '')}")
        for line_id, line in area.get("lines", {}).items():
            devs = line.get("devices", [])
            lines.append(f"    Linie {area_id}.{line_id}: {line.get('name', '')} ({len(devs)} Geräte)")

    lines.append("\n## Geräte")
    for addr, dev in project_data.get("devices", {}).items():
        lines.append(f"  {addr}: {dev.get('name', '')} — {dev.get('manufacturer_name', '')} {dev.get('order_number', '')}")

    lines.append("\n## Gruppenadressen")
    for _, ga in project_data.get("group_addresses", {}).items():
        dpt = ga.get("dpt")
        dpt_str = f" [DPT {dpt['main']}.{str(dpt.get('sub') or 0).zfill(3)}]" if dpt and dpt.get("main") else ""
        lines.append(f"  {ga.get('address', '')}: {ga.get('name', '')}{dpt_str}")

    funcs = project_data.get("functions", {})
    if funcs:
        lines.append("\n## Funktionen")
        for _, func in funcs.items():
            gas = [v.get("address", "") for v in (func.get("group_addresses") or {}).values()]
            lines.append(f"  {func.get('name', '')}: {', '.join(gas)}")

    return "\n".join(lines)


@app.get("/api/llm/config")
def get_llm_config():
    cfg = load_config()
    key = cfg.get("openrouter_api_key", "")
    return {
        "configured": bool(key),
        "model": cfg.get("llm_model", LLM_DEFAULT_MODEL),
    }


@app.post("/api/llm/config")
async def set_llm_config(data: dict):
    cfg = load_config()
    if "api_key" in data:
        cfg["openrouter_api_key"] = data["api_key"]
    if "model" in data:
        cfg["llm_model"] = data["model"] or LLM_DEFAULT_MODEL
    save_config(cfg)
    return {"ok": True}


@app.post("/api/llm/analyze")
async def llm_analyze(data: dict):
    cfg = load_config()
    api_key = cfg.get("openrouter_api_key", "")
    model = cfg.get("llm_model", LLM_DEFAULT_MODEL)
    question = data.get("question", "").strip() or "Erkläre das Projekt, seine Topologie und die wichtigsten Gruppenadressen."

    if not api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API-Key nicht konfiguriert")
    if not state["project_data"]:
        raise HTTPException(status_code=400, detail="Kein Projekt geladen")

    summary = _build_project_summary(state["project_data"])
    messages = [
        {
            "role": "system",
            "content": (
                "Du bist ein KNX-Experte. KNX ist ein offener Standard für Gebäudeautomation. "
                "Analysiere das folgende KNX-Projekt und beantworte Fragen dazu. "
                "Antworte auf Deutsch, präzise und strukturiert."
            ),
        },
        {
            "role": "user",
            "content": f"Projektdaten:\n\n{summary}\n\nFrage: {question}",
        },
    ]

    async def stream_llm():
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": messages, "stream": True},
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"data: {json.dumps({'error': body.decode()})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"

    return StreamingResponse(stream_llm(), media_type="text/event-stream")


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
