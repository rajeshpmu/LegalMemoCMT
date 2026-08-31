#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
MACHINE_CSV="${MACHINE_CSV:?Set MACHINE_CSV}"
CANDIDATES_CSV="${CANDIDATES_CSV:?Set CANDIDATES_CSV}"
OUTPUT_CSV="${OUTPUT_CSV:?Set OUTPUT_CSV}"
SUMMARY_JSON="${SUMMARY_JSON:?Set SUMMARY_JSON}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/build_clancy_basic_emotion_review_manifest.py" \
  --machine-csv "$MACHINE_CSV" \
  --candidates-csv "$CANDIDATES_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
