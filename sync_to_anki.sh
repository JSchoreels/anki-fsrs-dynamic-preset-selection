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

python3 - "$ADDON_DIR/meta.json" "$ROOT/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

meta_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])

meta = {}
if meta_path.exists():
    meta = json.loads(meta_path.read_text(encoding="utf8"))

manifest = json.loads(manifest_path.read_text(encoding="utf8"))

for key in ("name", "homepage", "human_version"):
    if not meta.get(key) and manifest.get(key):
        meta[key] = manifest[key]

meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf8")
PY

echo "Synced FSRS Dynamic Preset Selection to $ADDON_DIR"
