# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Setup** (creates `.venv/`, installs dependencies including `xknxproject` from `../xknxproject/`):
```bash
./setup.sh
```

**Run** (auto-runs setup if needed, starts server on `0.0.0.0:8002`):
```bash
./run.sh
# or directly (without --reload to avoid competing KNX tunnel connections):
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8002
```

> **Important:** Do not use `--reload` in production — it spawns multiple worker processes that each try to open a KNX tunnel, competing for the single tunnel slot on the gateway and causing connection failures.

**Autostart** (macOS LaunchAgent — starts server on every login):
```bash
./install-autostart.sh    # install & start immediately
./uninstall-autostart.sh  # remove
```
Logs are written to `logs/stdout.log`, `logs/stderr.log`, and `logs/knx_bus.log`.

There are no test or lint commands configured.

Test `.knxproj` files are available at `../xknxproject/test/resources/*.knxproj`.

## Architecture

This is a minimal two-file application — `server.py` (backend) and `index.html` (frontend SPA).

### Backend (`server.py`)

FastAPI with a lifespan context manager that starts the KNX connection task on startup.

#### Global state (`state` dict)
```python
state = {
    "xknx": None,              # active XKNX instance (or None)
    "connected": False,         # current gateway connection status
    "gateway_ip": "",
    "gateway_port": 3671,
    "project_data": None,       # last parsed project (for name lookups)
    "ga_dpt_map": {},           # {ga_address: dpt_dict} from project — registered with xknx
    "current_values": {},       # {ga_address: {"value": str, "ts": str}}
    "telegram_buffer": deque(maxlen=500),  # ring buffer replayed to new WS clients
    "ws_clients": set(),        # active WebSocket connections
    "connect_task": None,       # asyncio Task running knx_connect_loop()
}
```

#### API routes
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves `index.html` |
| `GET` | `/api/gateway` | Returns `{ip, port, connected}` |
| `POST` | `/api/gateway` | Saves `{ip, port}` to `config.json`, restarts KNX connection |
| `POST` | `/api/parse` | Parses uploaded `.knxproj` file; registers DPT map with xknx |
| `GET` | `/api/current-values` | Returns `current_values` dict |
| `GET` | `/api/log?lines=N` | Returns last N entries from `logs/knx_bus.log` as JSON |
| `GET` | `/api/annotations` | Returns `annotations.json` |
| `POST` | `/api/annotations` | Saves annotations dict to `annotations.json` |
| `WS` | `/ws` | WebSocket: sends `status`, `snapshot`, `history` on connect; streams `telegram` messages live |
| `GET` | `/.well-known/appspecific/com.chrome.devtools.json` | Returns `{}` (suppresses Chrome DevTools 404 noise) |

#### KNX connection (`knx_connect_loop`)
- Runs as a background `asyncio.Task` started in the lifespan
- Reads gateway config from `config.json` on each (re)start
- Connects via `xknx` tunneling; registers `telegram_received_cb`
- Registers current `ga_dpt_map` with `xknx.group_address_dpt` so xknx decodes telegrams automatically
- On disconnect: exponential backoff retry (10 → 20 → 40 → 60 s max)
- `start_connect_task()` cleanly cancels the old task before starting a new one (called on gateway config change)

#### DPT-aware decoding
When a `.knxproj` file is parsed, the GA→DPT mapping is registered with the live xknx instance:
```python
xknx.group_address_dpt.set(state["ga_dpt_map"])
```
xknx then sets `telegram.decoded_data` on each incoming telegram. `_process_telegram` uses this:
- `decoded_data.value` → typed Python value (float, int, bool, enum)
- `decoded_data.transcoder.unit` → unit string (e.g. `"°C"`, `"%"`, `"V"`)
- Booleans displayed as `"Ein"` / `"Aus"`, floats formatted to 2 decimal places
- Falls back to raw `telegram.payload.value` string if no DPT known

#### Telegram callback
`telegram_received_cb` is synchronous (required by xknx); it spawns `_process_telegram` as an `asyncio.Task`. The async function looks up device name and GA name from `project_data`, formats the value, logs to `knx_bus.log`, updates `current_values`, appends to `telegram_buffer`, and broadcasts to all WebSocket clients.

#### Log file
`logs/knx_bus.log` — pipe-separated format:
```
2024-01-15 14:32:01.234 | 1.1.5 | Taster EG | 1/2/3 | Licht Küche | Ein
```
Rotates daily, keeps 30 days. Pre-loaded into `telegram_buffer` on startup (last 500 lines).

#### Persistent files
- `config.json` — `{"gateway_ip": "...", "gateway_port": 3671}`
- `annotations.json` — `{"devices": {"1.1.5": {"name": "...", "description": "..."}}, "group_addresses": {"1/2/3": {...}}}`

---

### Frontend (`index.html`)

Vanilla HTML with Alpine.js v3 (state management) and Tailwind CSS (styling), all loaded from CDN. No build step.

#### Two phases

1. **Upload phase** — drag-and-drop or file picker, optional password/language inputs; button "Ohne Projektdatei → Nur Bus-Monitor" jumps straight to result phase with Bus-Monitor active
2. **Result phase** — eight tabs (see below)

#### Alpine.js state (key additions for live features)
```javascript
ws, wsStatus,                        // WebSocket instance and status ('connected'/'disconnected')
gatewayIP, gatewayPort,              // current gateway config
showGatewayConfig,                   // modal visibility
currentValues,                       // {ga_address: {value, ts}} — updated live
liveLog,                             // array of telegram entries, newest first (max 1000)
liveLogFilter, liveLogPaused,        // bus monitor controls
annotations,                         // loaded from /api/annotations
editingKey, editValue,               // inline edit state ('type|key|field' format)
```

#### WebSocket message types
| Type | Direction | Payload |
|------|-----------|---------|
| `status` | server→client | `{connected, ip, port}` — sent on connect and on connection change |
| `snapshot` | server→client | `{values: current_values}` — sent on WebSocket connect |
| `history` | server→client | `{entries: [...]}` — last 500 telegrams, newest first, sent on connect |
| `telegram` | server→client | `{ts, src, device, ga, ga_name, value}` — live stream |

Alpine.js uses array spread (`[msg, ...liveLog].slice(0, 1000)`) for live updates — **not** `unshift()` — to ensure Alpine's reactivity proxy detects the change.

#### Tab features

**With project file loaded:**
- **Info**: project metadata
- **Geräte**: searchable device table; `▸/▾` to expand KOs inline; "N KOs" link navigates to KO tab
- **Gruppenadressen**: searchable; "Letzter Wert" column shows live value from `currentValues`; linked KO badges navigate to KO tab
- **Topologie**: collapsible area → line → device tree
- **Kommunikationsobjekte**: COs grouped by device, collapsible; search auto-expands sections; row click navigates to GA tab
- **Funktionen**: function groups with linked GAs
- **DPT/Flags tooltips**: hover on DPT or Flags cell for human-readable description

**Without project file (bus-only mode):**
- **Geräte** tab shows bus-derived devices (`busDevices` getter — unique `src` addresses from `liveLog`); names/descriptions editable inline
- **Gruppenadressen** tab shows bus-derived GAs (`busGAs` getter — unique `ga` addresses from `liveLog`); names/descriptions editable inline

#### Inline editing (bus-only tabs)
- `startEdit(type, key, field, current)` sets `editingKey = 'type|key|field'`
- `saveEdit()` parses the key, updates `annotations`, triggers reactivity via object spread, POSTs to `/api/annotations`

#### Bus-Monitor tab
- Real-time telegram table (Zeit, PA, Gerät, GA, GA-Name, Wert)
- Filter input searches across all fields
- Pause/Resume button, Clear button, entry count
- Clicking a GA address navigates to Gruppenadressen tab

#### Export
- **With project**: `exportMarkdown()` / `exportPDF()` — full project data
- **Bus-only**: `_exportBusMarkdown()` / `_exportBusPDF()` — bus-derived devices + GAs with annotations

#### Cross-tab navigation
- CO tab row → `navigateToGA(co)`: switches to GA tab, sets `gaSearch`
- GA tab KO badge → `navigateToCO(coId)`: switches to KO tab, expands device section, highlights row yellow (`highlightedCO`)
- Devices tab "N KOs" link → `navigateToDeviceCOs(addr)`: switches to KO tab, expands device section
- Bus-Monitor GA click → switches to GA tab
- Devices tab KO row → `navigateToCO` via `$el.dataset.coKey` (data-attribute pattern to avoid Alpine.js nested x-for scope issues)

#### Gateway config modal
- ⚙ button in header opens modal; saves IP/port via `POST /api/gateway`; closes with ESC or Cancel

---

### Data flow

```
Upload .knxproj
  → POST /api/parse
  → xknxproject parses file
  → state["project_data"] + state["ga_dpt_map"] updated
  → xknx.group_address_dpt.set(ga_dpt_map)   ← DPT decoder registered
  → JSON returned to frontend → Alpine.js renders tabs

KNX telegram received
  → xknx decodes via group_address_dpt (if DPT known)
  → telegram_received_cb → _process_telegram
  → logs to knx_bus.log
  → current_values[ga] updated
  → telegram_buffer.append(entry)
  → broadcast to all WebSocket clients
  → frontend: currentValues updated, liveLog prepended
```

---

### xknxproject output structure (key field names)
The frontend is tightly coupled to these field names — mismatches were the source of most bugs:
- `project.devices` — flat dict keyed by `individual_address`; fields: `name`, `manufacturer_name`, `application`, `order_number`, `communication_object_ids`
- `project.topology` — dict keyed by area address string; `Area` has `name`, `lines` (dict keyed by line address string); `Line` has `name`, `devices` (list of address strings, **not** device objects)
- `project.communication_objects` — flat dict; fields: `name`, `number`, `device_address`, `dpts` (list), `flags` (nested: `read`, `write`, `transmit`, `update`, `communication`, `read_on_init`), `group_address_links`
- `project.group_addresses` — flat dict; fields: `address`, `name`, `dpt` (single object or null), `description`, `communication_object_ids`
- `project.functions` — dict; `group_addresses` field is a **dict** of `{id: {address, name, role}}`, not a list
- `project.info` — fields: `name` (not `project_name`), `tool_version` (not `project_version`)

### Key dependencies
- `xknxproject` — installed in editable mode from sibling directory `../xknxproject/`; handles all `.knxproj` parsing
- `xknx` — installed from PyPI; handles KNX/IP tunneling, telegram routing, and DPT decoding via `group_address_dpt`
- `websockets` — required by FastAPI for WebSocket support
