#!/usr/bin/env bash
set -euo pipefail

# Paper-exact MELD workflow template.
#
# Intended to mirror the MemoCMT paper as closely as possible:
# - BERT text encoder + HuBERT audio encoder
# - bidirectional cross-attention CMT
# - MIN pooling for the MELD headline result
# - MELD 5-fold CV over train/dev dialogues
# - held-out MELD test evaluation per fold
#
# Paper schedule reference:
# - Adam
# - lr = 1e-4
# - beta1 = 0.9, beta2 = 0.999
# - step LR decay by 0.1 every 30 epochs
# - train up to 100 epochs with best validation checkpoint
#
# This script is prepared as the paper-exact orchestration layer. Execute it only
# once the training loop is configured for the paper schedule you want to use.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="data/manifests/meld_raw.csv"
MELD_CV_DIR="data/manifests/meld_cv"
RESULTS_DIR="results/paper_exact_meld_cv/cmt_min"

mkdir -p results/paper_exact_meld_cv

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
    --epochs 100 \
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

echo "Paper-exact MELD 5-fold CV template complete."
