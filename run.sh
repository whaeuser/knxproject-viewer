#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -f "$VENV_DIR/bin/uvicorn" ]; then
  echo "Virtuelle Umgebung nicht gefunden. Führe setup.sh aus …"
  bash "$SCRIPT_DIR/setup.sh"
fi

echo "==> Starte KNX Project Viewer auf http://0.0.0.0:8000"
cd "$SCRIPT_DIR"
exec "$VENV_DIR/bin/uvicorn" server:app --host 0.0.0.0 --reload
