#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_CSV="${INPUT_CSV:?Set INPUT_CSV}"
OUTPUT_DIR="${OUTPUT_DIR:?Set OUTPUT_DIR}"
SUMMARY_JSON="${SUMMARY_JSON:?Set SUMMARY_JSON}"
REPORT_TXT="${REPORT_TXT:?Set REPORT_TXT}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/eda_non_neutral_recovery.py" \
  --input-csv "$INPUT_CSV" \
  --output-dir "$OUTPUT_DIR" \
  --summary-json "$SUMMARY_JSON" \
  --report-txt "$REPORT_TXT" \
  "$@"
