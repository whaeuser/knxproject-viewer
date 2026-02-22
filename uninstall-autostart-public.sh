#!/usr/bin/env bash
set -euo pipefail

PLIST_LABEL="com.knxproject-viewer-public"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

if [ -f "$PLIST_DST" ]; then
  launchctl unload -w "$PLIST_DST" 2>/dev/null || true
  rm "$PLIST_DST"
  echo "==> Autostart (public) entfernt."
else
  echo "==> Kein Autostart gefunden ($PLIST_DST)."
fi
