#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ADDON_DIR="/Users/jschoreels/Library/Application Support/Anki2/addons21/1798968356"

mkdir -p "$ADDON_DIR"

rsync -a --delete "$ROOT/fsrs_dynamic_preset_selection/" "$ADDON_DIR/fsrs_dynamic_preset_selection/"
rsync -a \
  "$ROOT/__init__.py" \
  "$ROOT/manifest.json" \
  "$ROOT/config.json" \
  "$ROOT/config.schema.json" \
  "$ROOT/config.md" \
  "$ROOT/README.md" \
  "$ADDON_DIR/"

echo "Synced FSRS Dynamic Preset Selection to $ADDON_DIR"
