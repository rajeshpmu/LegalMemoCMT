#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_utterance_manifest.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_dataset_manifest.csv}"
TRAIN_CSV="${TRAIN_CSV:-$ROOT_DIR/data/processed/phase2/clancy/train.csv}"
DEV_CSV="${DEV_CSV:-$ROOT_DIR/data/processed/phase2/clancy/dev.csv}"
TEST_CSV="${TEST_CSV:-$ROOT_DIR/data/processed/phase2/clancy/test.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_dataset_split_summary.json}"

"$PYTHON_BIN" phase2/build_clancy_dataset_split.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --train-csv "$TRAIN_CSV" \
  --dev-csv "$DEV_CSV" \
  --test-csv "$TEST_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
