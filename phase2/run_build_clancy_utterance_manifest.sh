#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

RAW_ROOT="${RAW_ROOT:-$ROOT_DIR/data/phase2/clancy/corpus/raw}"
SOURCE_MANIFEST="${SOURCE_MANIFEST:-$ROOT_DIR/data/processed/phase2/clancy/clancy_source_manifest.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_utterance_manifest.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_utterance_summary.json}"

"$PYTHON_BIN" phase2/build_clancy_utterance_manifest.py \
  --raw-root "$RAW_ROOT" \
  --source-manifest "$SOURCE_MANIFEST" \
  --output-csv "$OUTPUT_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
