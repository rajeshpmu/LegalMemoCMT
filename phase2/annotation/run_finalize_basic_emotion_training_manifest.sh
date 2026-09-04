#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_CSV="${INPUT_CSV:?Set INPUT_CSV}"
OUTPUT_CSV="${OUTPUT_CSV:?Set OUTPUT_CSV}"
TRAIN_CSV="${TRAIN_CSV:?Set TRAIN_CSV}"
DEV_CSV="${DEV_CSV:?Set DEV_CSV}"
TEST_CSV="${TEST_CSV:?Set TEST_CSV}"
SUMMARY_JSON="${SUMMARY_JSON:?Set SUMMARY_JSON}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/finalize_basic_emotion_training_manifest.py" \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --train-csv "$TRAIN_CSV" \
  --dev-csv "$DEV_CSV" \
  --test-csv "$TEST_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
