#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
"$PYTHON_BIN" scripts/resume_meld_vit_facecue_fold.py \
  --fold 4 \
  --manifest-dir "${FACECROP_CONTROL_CV_DIR:-data/manifests/meld_vit_facecrop_control_cv}" \
  --raw-manifest "${FACECROP_MANIFEST:-data/manifests/meld_vit_facecrop.csv}" \
  --baseline-dir "${FACECROP_BASELINE_DIR:-results/paper_aligned_meld_cv/cmt_min}" \
  --output-root "${FACECROP_GATED_OUTPUT_ROOT:-results/facial_cues/meld_vit_facecrop_gated}" \
  --modalities "${FACECROP_MODALITIES:-text,audio,video}" \
  --fusion-pooling "${FACECROP_POOLING:-min}" \
  --fusion-mode gated \
  --encoder-mode "${FACECROP_ENCODER_MODE:-paper}" \
  --selection-metric "${FACECROP_SELECTION_METRIC:-weighted_f1}" \
  "$@"
