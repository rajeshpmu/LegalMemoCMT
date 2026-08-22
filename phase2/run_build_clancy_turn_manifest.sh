#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_training_manifest_weak.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_turn_manifest.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_turn_manifest_summary.json}"
ISSUES_CSV="${ISSUES_CSV:-$ROOT_DIR/reports/phase2/clancy_turn_manifest_issues.csv}"

"$PYTHON_BIN" phase2/build_clancy_turn_manifest.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --summary-json "$SUMMARY_JSON" \
  --issues-csv "$ISSUES_CSV" \
  "$@"
