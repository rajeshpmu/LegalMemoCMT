#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/legalmeld_validated/legalmeld_metadata_validated.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/data/processed/phase2/legalmeld_validated/witness_only_rows}"
BASE_NAME="${BASE_NAME:-witness_rows}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/filter_legalmeld_rows_by_witness_role.py" \
  --input-csv "$INPUT_CSV" \
  --output-dir "$OUTPUT_DIR" \
  --base-name "$BASE_NAME" \
  "$@"
