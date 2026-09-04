#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/tupac/witness_only_v2/tupac_witness_speaking_review.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_witness_speaking_validated.csv}"
REJECTIONS_CSV="${REJECTIONS_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_witness_speaking_rejections.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/tupac_witness_speaking_validation.json}"

"$PYTHON_BIN" phase2/finalize_tupac_witness_speaking_manifest.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --rejections-csv "$REJECTIONS_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
