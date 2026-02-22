# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Setup** (creates `.venv/`, installs all dependencies including `xknxproject` from `../xknxproject/`):
```bash
./setup.sh
```

**Run — private server** (with bus monitor, port 8002):
```bash
./run.sh
# or directly:
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8002
```

**Run — public server** (no bus monitor, safe for internet, port 8004):
```bash
./run_public.sh
# or directly:
.venv/bin/uvicorn server_public:app --host 0.0.0.0 --port 8004
```

Both servers can run simultaneously and share the same `index.html`. The frontend fetches `/api/mode` on startup to activate or deactivate bus features.

> **Important:** Do not use `--reload` — it spawns multiple worker processes that each try to open a KNX tunnel, competing for the single tunnel slot on the gateway and causing connection failures.

**Autostart** (macOS LaunchAgent — starts server on every login):
```bash
./install-autostart.sh          # private server on port 8002
./install-autostart-public.sh   # public server on port 8004
./uninstall-autostart.sh        # remove private autostart
./uninstall-autostart-public.sh # remove public autostart
```
Both LaunchAgents call uvicorn directly (no `--reload`) on their respective ports.
Logs are written to `logs/stdout.log`, `logs/stderr.log`, and `logs/knx_bus.log`.

There are no test or lint commands configured.

Test `.knxproj` files are available at `../xknxproject/test/resources/*.knxproj`.

## Architecture

This is a minimal application — two server files sharing one `index.html` frontend SPA.

### Backend

Two server files:
- **`server.py`** — private server (port 8002): full features including KNX live connection, WebSocket, bus monitor, annotations
- **`server_public.py`** — public server (port 8004): read-only, only `GET /`, `GET /api/mode`, `POST /api/parse`; no KNX connection, no WebSocket, no state

`server.py` uses a FastAPI lifespan context manager that starts the KNX connection task on startup.

#### Global state (`state` dict)
```python
state = {
    "xknx": None,              # active XKNX instance (or None)
    "connected": False,         # current gateway connection status
    "gateway_ip": "",
    "gateway_port": 3671,
    "language": "de-DE",        # language for .knxproj parsing (de-DE or en-US)
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
| `GET` | `/api/mode` | Returns `{public: false}` — signals full-feature mode to frontend |
| `GET` | `/api/gateway` | Returns `{ip, port, connected, language}` |
| `POST` | `/api/gateway` | Saves `{ip, port, language}` to `config.json`, restarts KNX connection |
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
- `config.json` — `{"gateway_ip": "...", "gateway_port": 3671, "language": "de-DE"}`
- `annotations.json` — `{"devices": {"1.1.5": {"name": "...", "description": "..."}}, "group_addresses": {"1/2/3": {...}}}`

---

### Frontend (`index.html`)

Vanilla HTML with Alpine.js v3 (state management) and Tailwind CSS (styling), all loaded from CDN. No build step.

#### Startup (`init()`)
Fetches `/api/mode` first. If `public: true`, sets `publicMode = true` and skips WebSocket and annotations. If `public: false` (default), connects WebSocket and loads annotations.

#### Two phases

1. **Upload phase** — drag-and-drop or file picker, optional password input; language from gateway config is used automatically; button "Ohne Projektdatei → Nur Bus-Monitor" jumps to result phase (hidden in public mode)
2. **Result phase** — eight tabs (see below)

#### Alpine.js state (key additions for live features)
```javascript
publicMode,                          // true when served by server_public.py — disables all bus features
ws, wsStatus,                        // WebSocket instance and status ('connected'/'disconnected')
gatewayIP, gatewayPort,              // current gateway config
gatewayLanguage,                     // 'de-DE' (default) or 'en-US' — persisted in config.json
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
| `status` | server→client | `{connected, ip, port, language}` — sent on connect and on connection change |
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
- **Funktionen**: function groups with linked GAs — tab only shown when project contains ≥1 function (via `visibleTabs`)
- **Bus-Monitor**: hidden entirely in public mode (via `visibleTabs`)
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
- ⚙ button in header opens modal; fields: IP address, port, language (select: de-DE / en-US)
- Saves all three via `POST /api/gateway`; language is used automatically on next `.knxproj` parse
- Closes with ESC or Cancel; language field on the upload form was removed in favour of this persistent setting

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
