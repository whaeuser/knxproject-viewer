# KNX Project Viewer

[🇩🇪 Deutsch](README.de.md) | 🇬🇧 English

> **Vibe Coded** — this project was built entirely with [Claude Code](https://claude.ai/code).
>
> **Demo:** [knxviewer.nurdaheim.net](https://knxviewer.nurdaheim.net/)

Web UI for uploading, analysing and documenting `.knxproj` files – with an optional live bus monitor for KNX/IP gateways.

**Stack:** FastAPI · Alpine.js · Tailwind CSS · xknxproject · xknx

---

## Features

### Project Viewer (both modes)
- Upload `.knxproj` file (drag & drop or file picker), optional password support
- **Info** – project metadata
- **Devices** – searchable table; expandable communication object list per device
- **Group Addresses** – searchable; DPT, description, linked COs
- **Topology** – area → line → devices (collapsible)
- **Locations** – building → floor → room → functions (collapsible)
- **Communication Objects** – all COs of all devices, searchable, grouped by device
- **Functions** – only shown when the project contains at least one function
- Cross-tab navigation: CO → GA, GA → CO, device → COs
- DPT and flags tooltips (100+ types)
- Export as Markdown or PDF

### Live Bus Monitor (private server only, port 8002)
- Real-time telegrams via WebSocket
- **DPT-aware decoding**: values with unit (`21.34 °C`, `75 %`, `On/Off`) when a project file is loaded
- Value cell tooltip shows DPT type and raw value, e.g. `DPT: 9.001 | Raw: DPTArray((0x0c, 0x1a))`
- **Last value** per group address shown in the GA table
- Persistent log with daily rotation (`logs/knx_bus.log`, 30 days), CSV export
- **Bus-only mode**: derive devices and GAs from bus telegrams without a project file
- Inline editing of names and descriptions → saved to `annotations.json`
- Connection indicator + gateway configuration (IP, port, language) in the browser
- **Last project file** is saved after parsing and automatically suggested on next start

---

## Setup & Usage

Requirement: Python 3.10+ must be installed on the system (all packages are installed into an isolated `.venv/`).

```bash
# One-time: create virtual environment and install packages
./openknxviewer setup

# Start private server — bus monitor, port 8002
./openknxviewer start
# → http://localhost:8002

# Start public server — project viewer only, port 8004
./openknxviewer start --public
# → http://localhost:8004

# Stop server(s)
./openknxviewer stop
./openknxviewer stop --public
./openknxviewer stop --all

# Show status (server + gateway connection)
./openknxviewer status

# Show bus log
./openknxviewer logs
./openknxviewer logs --lines 100
./openknxviewer logs --follow

# Show / set gateway configuration
./openknxviewer gateway
./openknxviewer gateway --ip 192.168.1.70 --port 3671 --language de-DE

# Update all packages
./openknxviewer update

# Set up autostart on login (macOS)
./openknxviewer autostart
./openknxviewer autostart --public
./openknxviewer autostart --remove
./openknxviewer autostart --remove --public
```

Both servers can run simultaneously.

### Windows

> **Note:** The Windows version (`openknxviewer.bat`) has not been tested yet.

```bat
openknxviewer setup
openknxviewer start
openknxviewer start --public
openknxviewer stop
openknxviewer status
openknxviewer logs --lines 100
openknxviewer gateway --ip 192.168.1.70
openknxviewer update
```

> Autostart on Windows: configure manually via Task Scheduler.

---

## Public / Private Mode

The frontend detects the mode automatically via `GET /api/mode`:

| | Private (port 8002) | Public (port 8004) |
|---|---|---|
| Project Viewer | ✓ | ✓ |
| Bus Monitor tab | ✓ | — |
| Last value (GA tab) | ✓ | — |
| Gateway configuration | ✓ | — |
| WebSocket | ✓ | — |
| Annotations | ✓ | — |
| KNX connection | ✓ | — |

---

## Gateway Configuration

Via the ⚙ button in the top right (private server only):
- KNX/IP gateway IP address and port
- Language for `.knxproj` parsing (`de-DE` default, `en-US` available)

Saved to `config.json`, loaded automatically on server start.
Can also be set via CLI: `./openknxviewer gateway --ip X.X.X.X`

---

## File Structure

```
knxproject-viewer/
├── server.py                    # Private server (port 8002): bus monitor, WebSocket, KNX
├── server_public.py             # Public server (port 8004): project viewer only
├── index.html                   # Single-page frontend (shared by both servers)
├── requirements.txt             # Python dependencies
├── openknxviewer                # CLI tool (macOS/Linux)
├── openknxviewer.bat            # CLI tool (Windows)
├── config.json                  # Gateway IP, port, language (auto-generated)
├── annotations.json             # Inline annotations (auto-generated)
├── last_project.json            # Last parsed project as JSON (auto-generated)
└── logs/
    ├── knx_bus.log              # KNX telegram log (daily rotation, 30 days)
    ├── stdout.log               # Server stdout
    ├── stderr.log               # Server stderr
    ├── stdout-public.log        # Server stdout (public)
    └── stderr-public.log        # Server stderr (public)
```

---

## Dependencies

```
fastapi
uvicorn[standard]
python-multipart
websockets
xknx
xknxproject
```

---

## License

This project is licensed under the **GNU General Public License v2** (GPL v2),
required by its dependency on [xknxproject](https://github.com/XKNX/xknxproject) (GPL v2).

This means: anyone is free to use, modify and redistribute the code —
provided that derivative works are also released under GPL v2.

See [LICENSE](LICENSE).

---

## Acknowledgements

This project would not be possible without these great open-source libraries:

| Library | Description | License |
|---|---|---|
| [xknxproject](https://github.com/XKNX/xknxproject) | Parses `.knxproj` files | GPL v2 |
| [xknx](https://github.com/XKNX/xknx) | KNX/IP communication and DPT decoding | MIT |
| [FastAPI](https://fastapi.tiangolo.com) | Modern Python web framework | MIT |
| [Alpine.js](https://alpinejs.dev) | Lightweight JavaScript framework | MIT |
| [Tailwind CSS](https://tailwindcss.com) | Utility-first CSS framework | MIT |

Many thanks to all maintainers and contributors of these projects!
