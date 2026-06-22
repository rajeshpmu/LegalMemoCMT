#!/usr/bin/env bash
set -euo pipefail

# Paper-aligned MELD workflow:
# - build a raw MELD manifest
# - split train/dev dialogues into 5 CV folds
# - train the paper-aligned CMT + MIN model on each fold
# - evaluate each fold on the held-out MELD test split

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="data/manifests/meld_raw.csv"
MELD_CV_DIR="data/manifests/meld_cv"
RESULTS_DIR="results/paper_aligned_meld_cv/cmt_min"

mkdir -p results/paper_aligned_meld_cv

"$PYTHON_BIN" scripts/build_meld_raw_manifest.py \
  --meld-root data/MELD \
  --manifest-dir data/manifests

"$PYTHON_BIN" scripts/build_meld_cv_folds.py \
  --manifest "$MELD_RAW_MANIFEST" \
  --output-dir "$MELD_CV_DIR" \
  --num-folds 5 \
  --seed 42 \
  --base-splits train,dev

for fold in 0 1 2 3 4; do
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
    --loss-type weighted-ce \
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

echo "Paper-aligned MELD 5-fold CV complete."
