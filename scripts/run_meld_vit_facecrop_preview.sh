#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

VIDEO_PATH="${1:-}"
if [ -z "$VIDEO_PATH" ]; then
  echo "Usage: bash scripts/run_meld_vit_facecrop_preview.sh <raw_video.mp4>" >&2
  echo "Example: bash scripts/run_meld_vit_facecrop_preview.sh data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia279_utt9.mp4" >&2
  exit 1
fi

OUTPUT_DIR="${OUTPUT_DIR:-results/facecrop_preview}"
NUM_FRAMES="${NUM_FRAMES:-6}"
FRAME_SIZE="${FRAME_SIZE:-224}"

"$PYTHON_BIN" scripts/preview_meld_vit_facecrop.py \
  --video-path "$VIDEO_PATH" \
  --output-dir "$OUTPUT_DIR" \
  --num-frames "$NUM_FRAMES" \
  --frame-size "$FRAME_SIZE"
