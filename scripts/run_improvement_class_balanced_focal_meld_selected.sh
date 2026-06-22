#!/usr/bin/env bash
set -euo pipefail

# Improvement step 1:
# Re-run selected MELD folds with class-balanced focal loss.
# This keeps the existing paper-aligned scripts intact and writes to a
# separate improvement results tree.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="${MELD_RAW_MANIFEST:-data/manifests/meld_raw.csv}"
MELD_CV_DIR="${MELD_CV_DIR:-data/manifests/meld_cv}"
RESULTS_DIR="${RESULTS_DIR:-results/improvement/class_balanced_focal/meld_selected/cmt_min}"
LOCK_FILE="${LOCK_FILE:-/tmp/LegalMemoCMT_class_balanced_focal.lock}"
SELECTED_FOLDS=(2 4)

mkdir -p "$(dirname "$RESULTS_DIR")"

if [ ! -f "$MELD_RAW_MANIFEST" ]; then
  echo "Missing MELD raw manifest: $MELD_RAW_MANIFEST" >&2
  echo "If you need to rebuild it for a new split, uncomment the build line below." >&2
  exit 1
fi

# Rebuild only if you intentionally want a new split directory.
# "$PYTHON_BIN" scripts/build_meld_raw_manifest.py \
#   --meld-root data/MELD \
#   --manifest-dir data/manifests

if [ -f "$LOCK_FILE" ]; then
  echo "Another improvement run appears to be active: $LOCK_FILE" >&2
  echo "Run the improvement scripts sequentially rather than in parallel." >&2
  exit 1
fi

trap 'rm -f "$LOCK_FILE"' EXIT
touch "$LOCK_FILE"

if [ ! -f "$MELD_CV_DIR/meld_fold_2_train.csv" ] || [ ! -f "$MELD_CV_DIR/meld_fold_4_train.csv" ]; then
  echo "Missing MELD fold CSVs in $MELD_CV_DIR" >&2
  echo "If you need a new split directory, uncomment the build command below." >&2
  exit 1
fi

# Rebuild only if you intentionally want a new split directory.
# "$PYTHON_BIN" scripts/build_meld_cv_folds.py \
#   --manifest "$MELD_RAW_MANIFEST" \
#   --output-dir "$MELD_CV_DIR" \
#   --num-folds 5 \
#   --seed 42 \
#   --base-splits train,dev

for fold in "${SELECTED_FOLDS[@]}"; do
  fold_dir="${RESULTS_DIR}/fold_${fold}"
  train_manifest="${MELD_CV_DIR}/meld_fold_${fold}_train.csv"
  val_manifest="${MELD_CV_DIR}/meld_fold_${fold}_val.csv"

  "$PYTHON_BIN" -m src.train.train \
    --manifest "$train_manifest" \
    --val-manifest "$val_manifest" \
    --output-dir "$fold_dir" \
    --encoder-mode paper \
    --fine-tune-backbones \
    --device cpu \
    --modalities "text,audio" \
    --loss-type focal \
    --focal-gamma 2.0 \
    --fusion-pooling min \
    --epochs 5 \
    --batch-size 4 \
    --lr 1e-4

  "$PYTHON_BIN" -m src.train.evaluate \
    --manifest "$MELD_RAW_MANIFEST" \
    --split test \
    --checkpoint "$fold_dir/best_model.pt" \
    --output-json "$fold_dir/metrics.json" \
    --output-predictions-csv "$fold_dir/predictions_test.csv" \
    --encoder-mode paper \
    --device cpu \
    --modalities "text,audio" \
    --fusion-pooling min \
    --batch-size 4
done

"$PYTHON_BIN" scripts/aggregate_fold_metrics.py \
  --input-dir "$RESULTS_DIR" \
  --pattern "fold_*/metrics.json" \
  --output-json "$RESULTS_DIR/summary.json" \
  --output-md "$RESULTS_DIR/summary.md"

echo "Improvement MELD selected-fold focal-loss run complete."
