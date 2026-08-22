#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_CSV="${INPUT_CSV:?Set INPUT_CSV to a Clancy duration manifest}"
OUTPUT_CSV="${OUTPUT_CSV:?Set OUTPUT_CSV for the new provenance-preserving CSV}"
CHECKPOINT="${CHECKPOINT:?Set CHECKPOINT to a seven-class Phase 1 MELD checkpoint}"
SUMMARY_JSON="${SUMMARY_JSON:?Set SUMMARY_JSON for the inference summary}"
MAX_ROWS="${MAX_ROWS:-0}"
BATCH_SIZE="${BATCH_SIZE:-4}"
MODALITIES="${MODALITIES:-text,audio,video}"
DEVICE="${DEVICE:-cpu}"

# Prevent an unnecessary TensorFlow import in transformers. Phase 1 inference
# uses the PyTorch checkpoint only, and this avoids a macOS native-runtime crash.
export USE_TF="${USE_TF:-0}"
export TRANSFORMERS_NO_TF="${TRANSFORMERS_NO_TF:-1}"

"$PYTHON_BIN" phase2/pseudo_label_clancy_with_phase1.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --checkpoint "$CHECKPOINT" \
  --summary-json "$SUMMARY_JSON" \
  --max-rows "$MAX_ROWS" \
  --batch-size "$BATCH_SIZE" \
  --modalities "$MODALITIES" \
  --device "$DEVICE" \
  "$@"
