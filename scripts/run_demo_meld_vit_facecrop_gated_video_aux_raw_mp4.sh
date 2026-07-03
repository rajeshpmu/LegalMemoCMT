#!/usr/bin/env bash
set -euo pipefail

SAMPLE_ID="${1:-}"
VIDEO_PATH="${2:-}"

if [ -z "$SAMPLE_ID" ] || [ -z "$VIDEO_PATH" ]; then
  echo "Usage: bash scripts/run_demo_meld_vit_facecrop_gated_video_aux_raw_mp4.sh <sample_id> <raw_video.mp4>" >&2
  exit 1
fi

CHECKPOINT="${CHECKPOINT:-results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt}"
VISION_MODE="${VISION_MODE:-facecrop}"
DEVICE="${DEVICE:-cpu}"

if [ ! -f "$CHECKPOINT" ]; then
  echo "Missing aux-loss checkpoint: $CHECKPOINT" >&2
  echo "Copy the checkpoint from Runpod or set CHECKPOINT to a valid local path." >&2
  exit 1
fi

CHECKPOINT="$CHECKPOINT" \
VISION_MODE="$VISION_MODE" \
DEVICE="$DEVICE" \
bash scripts/run_phase1_raw_mp4_demo.sh "$SAMPLE_ID" "$VIDEO_PATH"
