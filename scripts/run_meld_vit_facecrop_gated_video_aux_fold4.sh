#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
"$PYTHON_BIN" scripts/resume_meld_vit_facecue_fold.py \
  --fold 4 \
  --manifest-dir "${FACECROP_CONTROL_CV_DIR:-data/manifests/meld_vit_facecrop_control_cv}" \
  --raw-manifest "${FACECROP_MANIFEST:-data/manifests/meld_vit_facecrop.csv}" \
  --baseline-dir "${FACECROP_BASELINE_DIR:-results/paper_aligned_meld_cv/cmt_min}" \
  --output-root "${FACECROP_GATED_VIDEO_AUX_OUTPUT_ROOT:-results/facial_cues/meld_vit_facecrop_gated_video_aux}" \
  --modalities "${FACECROP_MODALITIES:-text,audio,video}" \
  --fusion-pooling "${FACECROP_POOLING:-min}" \
  --fusion-mode gated \
  --encoder-mode "${FACECROP_ENCODER_MODE:-paper}" \
  --lr "${FACECROP_LR:-2e-5}" \
  --epochs "${FACECROP_EPOCHS:-8}" \
  --early-stop-patience "${FACECROP_EARLY_STOP_PATIENCE:-2}" \
  --video-aux-weight "${FACECROP_VIDEO_AUX_WEIGHT:-0.1}" \
  --video-aux-loss-type "${FACECROP_VIDEO_AUX_LOSS_TYPE:-weighted-ce}" \
  --selection-metric "${FACECROP_SELECTION_METRIC:-weighted_f1}" \
  "$@"
