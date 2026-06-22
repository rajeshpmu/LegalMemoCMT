#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

#"$PYTHON_BIN" scripts/build_meld_vit_facecue_manifest.py "$@"
"$PYTHON_BIN" scripts/build_meld_cv_folds.py \
  --manifest "${FACECUE_MANIFEST:-data/manifests/meld_vit_facecue.csv}" \
  --output-dir "${FACECUE_CV_DIR:-data/manifests/meld_vit_facecue_cv}" \
  --base-splits "${FACECUE_BASE_SPLITS:-train,dev}" \
  --num-folds "${FACECUE_NUM_FOLDS:-5}" \
  --seed "${FACECUE_SEED:-42}"
