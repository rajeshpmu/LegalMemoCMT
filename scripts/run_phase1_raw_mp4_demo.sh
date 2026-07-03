#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/legalai-py311/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
fi

MANIFEST="${MANIFEST:-data/manifests/meld_test.csv}"
CHECKPOINT="${CHECKPOINT:-results/paper_aligned_meld_cv/cmt_min/fold_2/best_model.pt}"
DEVICE="${DEVICE:-cpu}"
VISION_MODE="${VISION_MODE:-facecrop}"
MODALITIES="${MODALITIES:-text,audio,video}"
FUSION_POOLING="${FUSION_POOLING:-}"
FUSION_MODE="${FUSION_MODE:-}"
ENCODER_MODE="${ENCODER_MODE:-}"
CACHE_DIR="${CACHE_DIR:-results/phase1_review_demo/raw_mp4_cache}"
OUTPUT_JSON="${OUTPUT_JSON:-}"

SAMPLE_ID="${1:-}"
VIDEO_PATH="${2:-}"

if [ -z "$SAMPLE_ID" ] || [ -z "$VIDEO_PATH" ]; then
  echo "Usage: bash scripts/run_phase1_raw_mp4_demo.sh <sample_id> <raw_video.mp4>" >&2
  echo "Example: bash scripts/run_phase1_raw_mp4_demo.sh test_dia143_utt2 data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia143_utt2.mp4" >&2
  exit 1
fi

if [ ! -f "$MANIFEST" ]; then
  echo "Missing manifest: $MANIFEST" >&2
  exit 1
fi
if [ ! -f "$CHECKPOINT" ]; then
  echo "Missing checkpoint: $CHECKPOINT" >&2
  exit 1
fi
if [ ! -f "$VIDEO_PATH" ]; then
  echo "Missing raw video: $VIDEO_PATH" >&2
  exit 1
fi

args=(
  --manifest "$MANIFEST"
  --checkpoint "$CHECKPOINT"
  --sample-id "$SAMPLE_ID"
  --video-path "$VIDEO_PATH"
  --vision-mode "$VISION_MODE"
  --device "$DEVICE"
  --modalities "$MODALITIES"
  --cache-dir "$CACHE_DIR"
)

if [ -n "$FUSION_POOLING" ]; then
  args+=(--fusion-pooling "$FUSION_POOLING")
fi
if [ -n "$FUSION_MODE" ]; then
  args+=(--fusion-mode "$FUSION_MODE")
fi
if [ -n "$ENCODER_MODE" ]; then
  args+=(--encoder-mode "$ENCODER_MODE")
fi
if [ -n "$OUTPUT_JSON" ]; then
  args+=(--output-json "$OUTPUT_JSON")
fi

"$PYTHON_BIN" scripts/predict_phase1_raw_mp4_demo.py "${args[@]}"
