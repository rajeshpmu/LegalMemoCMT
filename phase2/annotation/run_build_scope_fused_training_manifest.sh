#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/human_scope_suggestions_200.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/emotion_scope_fused_training_manifest_200.csv}"
ELIGIBLE_CSV="${ELIGIBLE_CSV:-$ROOT_DIR/data/processed/phase2/clancy/emotion_scope_fused_training_eligible_200.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_emotion_scope_fused_training_manifest_200.json}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/build_scope_fused_training_manifest.py" \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --eligible-csv "$ELIGIBLE_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
