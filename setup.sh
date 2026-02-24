#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "==> Erstelle virtuelles Environment in $VENV_DIR …"
python3 -m venv "$VENV_DIR"

echo "==> Installiere Abhängigkeiten …"
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" --quiet

echo ""
echo "Fertig! Server starten mit:"
echo "  ./openknxviewer start"
