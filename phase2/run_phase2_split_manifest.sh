#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/build_phase2_split_manifest.py" \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  "$@"
