#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -f "$VENV_DIR/bin/uvicorn" ]; then
  echo "==> Virtuelle Umgebung nicht gefunden, führe setup.sh aus …"
  "$SCRIPT_DIR/setup.sh"
fi

echo "==> Starte KNX Project Viewer (Public, kein Bus-Monitor) auf http://0.0.0.0:8004"
exec "$VENV_DIR/bin/uvicorn" server_public:app --host 0.0.0.0 --port 8004
