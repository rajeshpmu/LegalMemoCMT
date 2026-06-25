#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/workspace/LegalMemoCMT}"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [ -z "${HF_TOKEN:-}" ]; then
  echo "Warning: HF_TOKEN is not set. Hugging Face downloads may be rate-limited on RunPod."
fi

"$PYTHON_BIN" scripts/check_meld_vit_facecrop_embeddings.py \
  --manifest "${FACECROP_CONTROL_MANIFEST:-data/manifests/meld_vit_facecrop_control_cv/meld_fold_2_train.csv}" \
  --expected-feature-dim 768

"$PYTHON_BIN" scripts/resume_meld_vit_facecue_fold.py \
  --fold 2 \
  --manifest-dir "${FACECROP_CONTROL_CV_DIR:-data/manifests/meld_vit_facecrop_control_cv}" \
  --raw-manifest "${FACECROP_MANIFEST:-data/manifests/meld_vit_facecrop.csv}" \
  --baseline-dir "${FACECROP_BASELINE_DIR:-results/paper_aligned_meld_cv/cmt_min}" \
  --output-root "${FACECROP_GATED_VIDEO_AUX_OUTPUT_ROOT:-results/facial_cues/meld_vit_facecrop_gated_video_aux}" \
  --modalities "${FACECROP_MODALITIES:-text,audio,video}" \
  --fusion-pooling "${FACECROP_POOLING:-min}" \
  --fusion-mode gated \
  --encoder-mode "${FACECROP_ENCODER_MODE:-paper}" \
  --device "${FACECROP_DEVICE:-cuda}" \
  --num-workers "${FACECROP_NUM_WORKERS:-4}" \
  --pin-memory \
  --persistent-workers \
  --lr "${FACECROP_LR:-2e-5}" \
  --epochs "${FACECROP_EPOCHS:-8}" \
  --early-stop-patience "${FACECROP_EARLY_STOP_PATIENCE:-2}" \
  --video-aux-weight "${FACECROP_VIDEO_AUX_WEIGHT:-0.1}" \
  --video-aux-loss-type "${FACECROP_VIDEO_AUX_LOSS_TYPE:-weighted-ce}" \
  --selection-metric "${FACECROP_SELECTION_METRIC:-weighted_f1}" \
  "$@"
