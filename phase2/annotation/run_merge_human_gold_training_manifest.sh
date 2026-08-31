#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
MACHINE_CSV="${MACHINE_CSV:?Set MACHINE_CSV}"
HUMAN_CSV="${HUMAN_CSV:?Set HUMAN_CSV}"
OUTPUT_CSV="${OUTPUT_CSV:?Set OUTPUT_CSV}"
SUMMARY_JSON="${SUMMARY_JSON:?Set SUMMARY_JSON}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/merge_human_gold_training_manifest.py" \
  --machine-csv "$MACHINE_CSV" \
  --human-csv "$HUMAN_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
