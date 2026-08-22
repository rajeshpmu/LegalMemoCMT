#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/legalmeld_validated/legalmeld_metadata_validated.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/data/processed/phase2/legalmeld_validated/filtered_rows}"
BASE_NAME="${BASE_NAME:-legalmeld_rows}"
CATEGORIES="${CATEGORIES:-usable,review,reject,high_confidence,medium_confidence,low_confidence,video_valid,audio_valid,split_train,split_dev,split_test}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/filter_legalmeld_rows_by_use.py" \
  --input-csv "$INPUT_CSV" \
  --output-dir "$OUTPUT_DIR" \
  --base-name "$BASE_NAME" \
  --categories "$CATEGORIES" \
  "$@"
