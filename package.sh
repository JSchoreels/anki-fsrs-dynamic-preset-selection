#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"
OUT="$DIST/fsrs-dynamic-preset-selection.ankiaddon"

mkdir -p "$DIST"
rm -f "$OUT"
cd "$ROOT"
zip -r "$OUT" \
  __init__.py \
  manifest.json \
  config.json \
  config.schema.json \
  config.md \
  fsrs_dynamic_preset_selection \
  -x '*/__pycache__/*' '*.pyc'

echo "Wrote $OUT"

