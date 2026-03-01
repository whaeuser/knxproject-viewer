#!/usr/bin/env python3
"""
KNX Gateway Proxy — verbindet einen lokalen KNX-Bus (TUNNELING/IP) mit dem
OpenKNXViewer-Server über eine WebSocket-Verbindung (WSS + Token-Auth).

Verwendung:
    python3 knx_gateway_proxy.py \
        --server-url "wss://host/ws/remote-gateway?token=TOKEN" \
        --knx-ip 192.168.1.100 [--knx-port 3671] [--knx-type ip] [--ssl-no-verify]

Optionale Konfigurationsdatei (proxy_config.json im selben Verzeichnis):
    {"server_url": "...", "knx_ip": "...", "knx_port": 3671, "ssl_no_verify": false}

CLI-Argumente überschreiben Werte aus der Konfigurationsdatei.
"""

import argparse
import asyncio
import json
import logging
import ssl
import sys
from pathlib import Path

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError:
    sys.exit("Fehler: 'websockets' nicht installiert. Bitte: pip3 install websockets")

try:
    from xknx import XKNX
    from xknx.dpt import DPTArray, DPTBinary
    from xknx.io import ConnectionConfig, ConnectionType
    from xknx.telegram import Telegram
    from xknx.telegram.address import GroupAddress
    from xknx.telegram.apci import GroupValueRead, GroupValueWrite
except ImportError:
    sys.exit("Fehler: 'xknx' nicht installiert. Bitte: pip3 install xknx")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("knx_proxy")

_ws_conn = None          # aktive WebSocket-Verbindung zum Server
_current_xknx = None    # aktive xknx-Instanz


def _build_ssl_context(no_verify: bool):
    """Gibt None (System-CAs) oder einen SSL-Kontext ohne Zertifikatsprüfung zurück."""
    if no_verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None  # websockets nutzt dann die System-CAs


# ── Telegramm-Serialisierung ───────────────────────────────────────────────────

def _serialize_telegram(telegram: Telegram) -> dict | None:
    """Konvertiert ein xknx-Telegram in ein JSON-serialisierbares Dict."""
    payload = telegram.payload
    apci = type(payload).__name__  # "GroupValueWrite", "GroupValueRead", "GroupValueResponse"

    src = str(telegram.source_address)
    ga = str(telegram.destination_address)

    if isinstance(payload, GroupValueRead):
        return {"type": "telegram", "src": src, "ga": ga,
                "apci": apci, "payload_type": "none"}

    raw = payload.value
    if isinstance(raw, DPTBinary):
        p_type, p_val = "binary", raw.value
    elif isinstance(raw, DPTArray):
        p_type, p_val = "array", list(raw.value)
    else:
        log.warning("Unbekannter Payload-Typ: %s — Telegramm wird übersprungen", type(raw))
        return None

    return {"type": "telegram", "src": src, "ga": ga,
            "apci": apci, "payload_type": p_type, "payload_value": p_val}


# ── Callback: KNX-Telegramm empfangen ─────────────────────────────────────────

def telegram_received_cb(telegram: Telegram):
    """Wird von xknx synchron aufgerufen; delegiert an einen asyncio-Task."""
    loop = asyncio.get_event_loop()
    loop.create_task(_forward_telegram(telegram))


async def _forward_telegram(telegram: Telegram):
    """Serialisiert ein Telegramm und sendet es an den Server."""
    if _ws_conn is None:
        return
    msg = _serialize_telegram(telegram)
    if msg is None:
        return
    try:
        await _ws_conn.send(json.dumps(msg))
        log.debug("→ Server: %s %s %s", msg["apci"], msg["ga"], msg.get("payload_value", ""))
    except Exception as e:
        log.warning("Fehler beim Senden an Server: %s", e)


# ── Nachricht vom Server verarbeiten (write/read) ─────────────────────────────

async def handle_server_message(msg: dict):
    """Verarbeitet eine vom Server gesendete Anweisung."""
    if _current_xknx is None:
        log.warning("Nachricht vom Server ignoriert — kein KNX verbunden")
        return

    msg_type = msg.get("type")
    ga_str = msg.get("ga", "")

    if msg_type == "write":
        p_type = msg.get("payload_type", "array")
        p_val = msg.get("payload_value")
        if p_type == "binary":
            payload_obj = GroupValueWrite(DPTBinary(p_val))
        else:
            payload_obj = GroupValueWrite(DPTArray(tuple(p_val)))
        tg = Telegram(destination_address=GroupAddress(ga_str), payload=payload_obj)
        await _current_xknx.telegrams.put(tg)
        log.info("← Server: Schreibe GA %s = %s", ga_str, p_val)

    elif msg_type == "read":
        tg = Telegram(destination_address=GroupAddress(ga_str), payload=GroupValueRead())
        await _current_xknx.telegrams.put(tg)
        log.info("← Server: Lese GA %s", ga_str)

    else:
        log.warning("Unbekannter Nachrichtentyp vom Server: %s", msg_type)


# ── KNX-Verbindungsschleife ────────────────────────────────────────────────────

async def knx_loop(cfg: dict):
    """Verbindet mit dem lokalen KNX-Bus und versucht bei Trennung neu zu verbinden."""
    global _current_xknx

    knx_ip = cfg["knx_ip"]
    knx_port = cfg.get("knx_port", 3671)
    knx_type = cfg.get("knx_type", "ip")

    if knx_type == "usb":
        raise NotImplementedError(
            "USB/TPUART wird von xknx auf PyPI derzeit nicht unterstützt. "
            "Bitte verwende --knx-type ip mit einem KNX/IP-Gateway."
        )

    retry_delay = 10
    while True:
        xknx = XKNX(
            connection_config=ConnectionConfig(
                connection_type=ConnectionType.TUNNELING,
                gateway_ip=knx_ip,
                gateway_port=knx_port,
            )
        )
        _current_xknx = xknx
        try:
            async with xknx:
                xknx.telegram_queue.register_telegram_received_cb(telegram_received_cb)
                log.info("KNX verbunden: %s:%d", knx_ip, knx_port)
                retry_delay = 10
                # Status an Server senden
                if _ws_conn is not None:
                    try:
                        await _ws_conn.send(json.dumps({"type": "status", "connected": True, "hw_type": knx_type}))
                    except Exception:
                        pass
                await asyncio.Event().wait()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("KNX-Verbindung getrennt: %s — Neuversuch in %ds", e, retry_delay)
            if _ws_conn is not None:
                try:
                    await _ws_conn.send(json.dumps({"type": "status", "connected": False}))
                except Exception:
                    pass
            retry_delay = min(retry_delay * 2, 60)
        finally:
            _current_xknx = None

        try:
            await asyncio.sleep(retry_delay)
        except asyncio.CancelledError:
            break


# ── WebSocket-Verbindungsschleife zum Server ──────────────────────────────────

async def ws_loop(cfg: dict):
    """Verbindet mit dem OpenKNXViewer-Server via WebSocket und empfängt Befehle."""
    global _ws_conn

    server_url = cfg["server_url"]
    ssl_no_verify = cfg.get("ssl_no_verify", False)
    ssl_ctx = _build_ssl_context(ssl_no_verify) if server_url.startswith("wss://") else None

    retry_delay = 5
    while True:
        try:
            log.info("Verbinde mit Server: %s", server_url)
            async with websockets.connect(server_url, ssl=ssl_ctx) as ws:
                _ws_conn = ws
                log.info("Server-WebSocket verbunden")
                retry_delay = 5

                # KNX-Status senden falls bereits verbunden
                if _current_xknx is not None:
                    await ws.send(json.dumps({"type": "status", "connected": True,
                                              "hw_type": cfg.get("knx_type", "ip")}))

                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        await handle_server_message(msg)
                    except json.JSONDecodeError:
                        log.warning("Ungültige JSON-Nachricht vom Server: %s", raw_msg[:100])
                    except Exception as e:
                        log.error("Fehler bei Server-Nachricht: %s", e)

        except asyncio.CancelledError:
            break
        except ConnectionClosed as e:
            log.warning("Server-WebSocket getrennt (Code %s): %s — Neuversuch in %ds",
                        e.code, e.reason, retry_delay)
        except OSError as e:
            log.warning("Netzwerkfehler: %s — Neuversuch in %ds", e, retry_delay)
        except Exception as e:
            log.warning("WebSocket-Fehler: %s — Neuversuch in %ds", e, retry_delay)
        finally:
            _ws_conn = None
            retry_delay = min(retry_delay * 2, 60)

        try:
            await asyncio.sleep(retry_delay)
        except asyncio.CancelledError:
            break


# ── Hauptfunktion ──────────────────────────────────────────────────────────────

def _load_proxy_config() -> dict:
    """Lädt optionale Konfigurationsdatei proxy_config.json."""
    config_path = Path(__file__).parent / "proxy_config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except Exception as e:
            log.warning("proxy_config.json konnte nicht geladen werden: %s", e)
    return {}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KNX Gateway Proxy für OpenKNXViewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--server-url", help="WebSocket-URL des Servers (wss://...?token=TOKEN)")
    parser.add_argument("--knx-ip", help="IP-Adresse des KNX/IP-Gateways")
    parser.add_argument("--knx-port", type=int, default=3671, help="Port des KNX/IP-Gateways (Standard: 3671)")
    parser.add_argument("--knx-type", choices=["ip", "usb"], default="ip",
                        help="Verbindungstyp: ip (Standard) oder usb (noch nicht unterstützt)")
    parser.add_argument("--ssl-no-verify", action="store_true",
                        help="TLS-Zertifikatsprüfung deaktivieren (nur für lokale Tests)")
    return parser.parse_args()


async def main(cfg: dict):
    try:
        await asyncio.gather(
            knx_loop(cfg),
            ws_loop(cfg),
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    args = _parse_args()
    file_cfg = _load_proxy_config()

    # CLI überschreibt Datei-Konfiguration
    cfg = {**file_cfg}
    if args.server_url:
        cfg["server_url"] = args.server_url
    if args.knx_ip:
        cfg["knx_ip"] = args.knx_ip
    cfg["knx_port"] = args.knx_port if args.knx_port != 3671 else cfg.get("knx_port", 3671)
    cfg["knx_type"] = args.knx_type
    cfg["ssl_no_verify"] = args.ssl_no_verify or cfg.get("ssl_no_verify", False)

    if not cfg.get("server_url"):
        sys.exit("Fehler: --server-url ist erforderlich (oder in proxy_config.json definieren)")
    if not cfg.get("knx_ip"):
        sys.exit("Fehler: --knx-ip ist erforderlich (oder in proxy_config.json definieren)")

    log.info("KNX Gateway Proxy startet")
    log.info("  Server: %s", cfg["server_url"])
    log.info("  KNX:    %s:%d (%s)", cfg["knx_ip"], cfg["knx_port"], cfg["knx_type"])
    if cfg["ssl_no_verify"]:
        log.warning("  SSL-Zertifikatsprüfung deaktiviert!")

    try:
        asyncio.run(main(cfg))
    except NotImplementedError as e:
        sys.exit(f"Fehler: {e}")
