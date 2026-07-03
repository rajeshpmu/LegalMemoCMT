#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/legalai-py311/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
fi
MANIFEST="${MANIFEST:-data/manifests/meld_test.csv}"
CHECKPOINT="${CHECKPOINT:-results/paper_aligned_meld_cv/cmt_min/fold_2/best_model.pt}"
DEVICE="${DEVICE:-cpu}"
MODALITIES="${MODALITIES:-text,audio,video}"
FUSION_POOLING="${FUSION_POOLING:-}"
FUSION_MODE="${FUSION_MODE:-}"
ENCODER_MODE="${ENCODER_MODE:-}"
SAMPLE_ID="${1:-}"

if [ -z "$SAMPLE_ID" ]; then
  echo "Usage: bash scripts/run_phase1_single_video_demo.sh <sample_id>" >&2
  echo "Example: bash scripts/run_phase1_single_video_demo.sh test_dia0_utt0" >&2
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

args=(
  --manifest "$MANIFEST"
  --checkpoint "$CHECKPOINT"
  --sample-id "$SAMPLE_ID"
  --device "$DEVICE"
  --modalities "$MODALITIES"
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

"$PYTHON_BIN" scripts/predict_phase1_single_demo.py "${args[@]}"
