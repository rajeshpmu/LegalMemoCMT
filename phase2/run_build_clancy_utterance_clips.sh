#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_training_manifest_weak.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_training_manifest_clipped.csv}"
CLIP_ROOT="${CLIP_ROOT:-$ROOT_DIR/data/processed/phase2/clancy/utterance_clips}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_utterance_clip_summary.json}"
ISSUES_CSV="${ISSUES_CSV:-$ROOT_DIR/reports/phase2/clancy_utterance_clip_issues.csv}"
SOURCE_OFFSETS_CSV="${SOURCE_OFFSETS_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_source_offsets.csv}"

"$PYTHON_BIN" phase2/build_clancy_utterance_clips.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --clip-root "$CLIP_ROOT" \
  --summary-json "$SUMMARY_JSON" \
  --issues-csv "$ISSUES_CSV" \
  --source-offsets-csv "$SOURCE_OFFSETS_CSV" \
  "$@"
