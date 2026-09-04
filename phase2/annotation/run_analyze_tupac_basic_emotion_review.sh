#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_CSV="${INPUT_CSV:?Set INPUT_CSV}"
OUTPUT_CSV="${OUTPUT_CSV:?Set OUTPUT_CSV}"
SUMMARY_JSON="${SUMMARY_JSON:?Set SUMMARY_JSON}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/analyze_tupac_basic_emotion_review.py" \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
