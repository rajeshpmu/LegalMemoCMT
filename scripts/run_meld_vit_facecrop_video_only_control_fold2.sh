#!/usr/bin/env bash
set -euo pipefail

# Video-only control run for the MELD face-crop branch.
# This isolates whether the cropped ViT facial embeddings carry standalone signal.

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
"$PYTHON_BIN" scripts/resume_meld_vit_facecue_fold.py \
  --fold 2 \
  --manifest-dir "${FACECROP_CONTROL_CV_DIR:-data/manifests/meld_vit_facecrop_control_cv}" \
  --raw-manifest "${FACECROP_MANIFEST:-data/manifests/meld_vit_facecrop.csv}" \
  --baseline-dir "${FACECROP_BASELINE_DIR:-results/paper_aligned_meld_cv/cmt_min}" \
  --output-root "${FACECROP_VIDEO_ONLY_CONTROL_OUTPUT_ROOT:-results/facial_cues/meld_vit_facecrop_video_only_control}" \
  --modalities video \
  --fusion-pooling "${FACECROP_POOLING:-min}" \
  --encoder-mode "${FACECROP_ENCODER_MODE:-paper}" \
  --selection-metric "${FACECROP_SELECTION_METRIC:-weighted_f1}" \
  "$@"
