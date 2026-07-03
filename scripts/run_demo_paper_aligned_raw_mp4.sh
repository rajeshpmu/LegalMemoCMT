#!/usr/bin/env bash
set -euo pipefail

SAMPLE_ID="${1:-}"
VIDEO_PATH="${2:-}"

if [ -z "$SAMPLE_ID" ] || [ -z "$VIDEO_PATH" ]; then
  echo "Usage: bash scripts/run_demo_paper_aligned_raw_mp4.sh <sample_id> <raw_video.mp4>" >&2
  exit 1
fi

CHECKPOINT="${CHECKPOINT:-results/paper_aligned_meld_cv/cmt_min/fold_2/best_model.pt}"
VISION_MODE="${VISION_MODE:-facecrop}"
DEVICE="${DEVICE:-cpu}"

CHECKPOINT="$CHECKPOINT" \
VISION_MODE="$VISION_MODE" \
DEVICE="$DEVICE" \
bash scripts/run_phase1_raw_mp4_demo.sh "$SAMPLE_ID" "$VIDEO_PATH"
