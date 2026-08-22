#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_turn_manifest_clipped.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_long_turn_review.csv}"
THRESHOLD_SECONDS="${THRESHOLD_SECONDS:-30}"

"$PYTHON_BIN" phase2/build_clancy_long_turn_review.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --threshold-seconds "$THRESHOLD_SECONDS" \
  "$@"
