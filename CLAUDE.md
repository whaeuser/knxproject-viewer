# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Setup** (creates `.venv/`, installs dependencies including `xknxproject` from `../xknxproject/`):
```bash
./setup.sh
```

**Run** (auto-runs setup if needed, starts server at http://localhost:8000):
```bash
./run.sh
# or directly:
.venv/bin/uvicorn server:app --reload
```

There are no test or lint commands configured.

Test `.knxproj` files are available at `../xknxproject/test/resources/*.knxproj`.

## Architecture

This is a minimal two-file application — `server.py` (backend) and `index.html` (frontend SPA).

### Backend (`server.py`)
FastAPI with two routes:
- `GET /` — serves `index.html`
- `POST /api/parse` — accepts multipart form: `file` (.knxproj), optional `password`, optional `language` (e.g. `de-DE`)

The endpoint saves the uploaded file to a temp path, delegates all parsing to `xknxproject` (installed from the sibling `../xknxproject/` directory), and returns a JSON blob. The temp file is cleaned up in a `finally` block.

Error mapping:
- `InvalidPasswordException` → HTTP 422
- `XknxProjectException` / general exceptions → HTTP 500

### Frontend (`index.html`)
Vanilla HTML with Alpine.js (state management) and Tailwind CSS (styling), all loaded from CDN. No build step.

The Alpine.js component drives two phases:
1. **Upload phase** — drag-and-drop or file picker, optional password/language inputs
2. **Result phase** — seven tabs displaying the parsed JSON: Info, Devices, Group Addresses, Topology, Locations, Communication Objects, Functions

The Topology and Locations tabs render recursive tree structures (Alpine.js template recursion via `x-html`). All data tabs with lists have real-time search filtering. Devices rows expand inline to show communication objects.

### Data flow
Upload → `POST /api/parse` → xknxproject parses .knxproj → JSON response → Alpine.js state update → tab UI renders.

### Key dependency
`xknxproject` is expected to exist as a sibling directory (`../xknxproject/`) and is installed in editable mode by `setup.sh`. All .knxproj parsing logic lives there, not in this repo.
