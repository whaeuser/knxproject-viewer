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
# or directly:
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8002 --reload
```

**Autostart** (macOS LaunchAgent — starts server on every login):
```bash
./install-autostart.sh    # install & start immediately
./uninstall-autostart.sh  # remove
```
Logs are written to `logs/stdout.log` and `logs/stderr.log`.

There are no test or lint commands configured.

Test `.knxproj` files are available at `../xknxproject/test/resources/*.knxproj`.

## Architecture

This is a minimal two-file application — `server.py` (backend) and `index.html` (frontend SPA).

### Backend (`server.py`)
FastAPI with three routes:
- `GET /` — serves `index.html`
- `POST /api/parse` — accepts multipart form: `file` (.knxproj), optional `password`, optional `language` (e.g. `de-DE`)
- `GET /.well-known/appspecific/com.chrome.devtools.json` — returns `{}` to suppress Chrome DevTools 404 log noise

The parse endpoint saves the uploaded file to a temp path, delegates all parsing to `xknxproject` (installed from the sibling `../xknxproject/` directory), and returns a JSON blob. The temp file is cleaned up in a `finally` block.

Error mapping:
- `InvalidPasswordException` → HTTP 422
- `XknxProjectException` / general exceptions → HTTP 500

### Frontend (`index.html`)
Vanilla HTML with Alpine.js (state management) and Tailwind CSS (styling), all loaded from CDN. No build step.

The Alpine.js component drives two phases:
1. **Upload phase** — drag-and-drop or file picker, optional password/language inputs
2. **Result phase** — seven tabs: Info, Geräte, Gruppenadressen, Topologie, Standorte, Kommunikationsobjekte, Funktionen

#### Tab features
- **Geräte**: searchable device table; each row has a `▸/▾` arrow to expand KOs inline, and an "N KOs" link that navigates to the Kommunikationsobjekte tab with that device pre-expanded. KO rows are clickable and jump to the corresponding entry on the KO tab.
- **Gruppenadressen**: searchable; linked KOs shown as clickable badges (`1.1.5 #12`) that jump to the KO tab with the target row highlighted in yellow.
- **Topologie**: collapsible area → line → device tree; device addresses looked up in `project.devices`.
- **Kommunikationsobjekte**: COs grouped by device in collapsible sections (default collapsed); sorted by KO number; clicking a row jumps to Gruppenadressen tab. Search auto-expands matching sections.
- **DPT/Flags tooltips**: hovering over any DPT or Flags cell shows a human-readable description (100+ DPT types mapped; flags spelled out individually).

#### Cross-tab navigation
- CO tab row → `navigateToGA(co)`: switches to GA tab, sets `gaSearch` to first linked address.
- GA tab KO badge → `navigateToCO(coId)`: switches to KO tab, expands device section, highlights row yellow (`highlightedCO` state).
- Devices tab "N KOs" link → `navigateToDeviceCOs(addr)`: switches to KO tab, expands device section.
- Devices tab KO row → `navigateToCO` via `$el.dataset.coKey` (data-attribute pattern used to avoid Alpine.js nested x-for scope issues).

#### Export
- **Markdown** (`exportMarkdown()`): generates a `.md` file with all project data (info, devices, GAs, COs grouped by device, topology, functions) and triggers a browser download.
- **PDF** (`exportPDF()`): generates a standalone HTML page with print-optimised CSS, opens it in a new tab, and auto-triggers `window.print()` after 500 ms so the user can save as PDF.

### Data flow
Upload → `POST /api/parse` → xknxproject parses .knxproj → JSON response → Alpine.js state update → tab UI renders.

### xknxproject output structure (key field names)
The frontend is tightly coupled to these field names — mismatches were the source of most bugs:
- `project.devices` — flat dict keyed by `individual_address`; fields: `name`, `manufacturer_name`, `application`, `order_number`, `communication_object_ids`
- `project.topology` — dict keyed by area address string; `Area` has `name`, `lines` (dict keyed by line address string); `Line` has `name`, `devices` (list of address strings, **not** device objects)
- `project.communication_objects` — flat dict; fields: `name`, `number`, `device_address`, `dpts` (list), `flags` (nested: `read`, `write`, `transmit`, `update`, `communication`, `read_on_init`), `group_address_links`
- `project.group_addresses` — flat dict; fields: `address`, `name`, `dpt` (single object or null), `description`, `communication_object_ids`
- `project.functions` — dict; `group_addresses` field is a **dict** of `{id: {address, name, role}}`, not a list
- `project.info` — fields: `name` (not `project_name`), `tool_version` (not `project_version`)

### Key dependency
`xknxproject` is expected to exist as a sibling directory (`../xknxproject/`) and is installed in editable mode by `setup.sh`. All .knxproj parsing logic lives there, not in this repo.
