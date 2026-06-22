#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

"$PYTHON_BIN" scripts/build_meld_vit_facecrop_manifest.py "$@"
"$PYTHON_BIN" scripts/build_meld_vit_facecrop_control_folds.py \
  --facecrop-manifest "${FACECROP_MANIFEST:-data/manifests/meld_vit_facecrop.csv}" \
  --paper-fold-dir "${FACECROP_PAPER_FOLD_DIR:-data/manifests/meld_cv}" \
  --output-dir "${FACECROP_CONTROL_CV_DIR:-data/manifests/meld_vit_facecrop_control_cv}" \
  --num-folds "${FACECROP_NUM_FOLDS:-5}"
