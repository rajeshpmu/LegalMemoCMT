#!/usr/bin/env bash
set -euo pipefail

# Warm-start improvement step:
# Resume Fold 2 and Fold 4 from the weighted-CE paper-aligned checkpoints,
# switch to focal loss, reduce the learning rate, and train for a few extra epochs.
# This does not modify or stop any existing training process.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="${MELD_RAW_MANIFEST:-data/manifests/meld_raw.csv}"
MELD_CV_DIR="${MELD_CV_DIR:-data/manifests/meld_cv}"
BASE_RESULTS_DIR="${BASE_RESULTS_DIR:-results/paper_aligned_meld_cv/cmt_min}"
OUTPUT_DIR="${OUTPUT_DIR:-results/improvement/warmstart_focal/meld_selected/cmt_min}"
SELECTED_FOLDS=(2 4)
FINE_TUNE_EPOCHS="${FINE_TUNE_EPOCHS:-3}"
FINE_TUNE_LR="${FINE_TUNE_LR:-5e-5}"

mkdir -p "$OUTPUT_DIR"

if [ ! -f "$MELD_RAW_MANIFEST" ]; then
  echo "Missing MELD raw manifest: $MELD_RAW_MANIFEST" >&2
  exit 1
fi

for fold in "${SELECTED_FOLDS[@]}"; do
  fold_train="${MELD_CV_DIR}/meld_fold_${fold}_train.csv"
  fold_val="${MELD_CV_DIR}/meld_fold_${fold}_val.csv"
  base_ckpt="${BASE_RESULTS_DIR}/fold_${fold}/best_model.pt"
  fold_out="${OUTPUT_DIR}/fold_${fold}"

  if [ ! -f "$fold_train" ] || [ ! -f "$fold_val" ]; then
    echo "Missing MELD fold CSVs for fold ${fold} in $MELD_CV_DIR" >&2
    exit 1
  fi
  if [ ! -f "$base_ckpt" ]; then
    echo "Missing base checkpoint for fold ${fold}: $base_ckpt" >&2
    exit 1
  fi

  mkdir -p "$fold_out"
  cp "$base_ckpt" "$fold_out/base_weighted_ce_checkpoint.pt"

  "$PYTHON_BIN" -m src.train.train \
    --manifest "$fold_train" \
    --val-manifest "$fold_val" \
    --output-dir "$fold_out" \
    --encoder-mode paper \
    --fine-tune-backbones \
    --device cpu \
    --modalities "text,audio" \
    --loss-type focal \
    --focal-gamma 2.0 \
    --fusion-pooling min \
    --epochs "$FINE_TUNE_EPOCHS" \
    --batch-size 4 \
    --lr "$FINE_TUNE_LR"

  "$PYTHON_BIN" -m src.train.evaluate \
    --manifest "$MELD_RAW_MANIFEST" \
    --split test \
    --checkpoint "$fold_out/best_model.pt" \
    --output-json "$fold_out/metrics.json" \
    --output-predictions-csv "$fold_out/predictions_test.csv" \
    --encoder-mode paper \
    --device cpu \
    --modalities "text,audio" \
    --fusion-pooling min \
    --batch-size 4
done

echo "Warm-start focal-loss MELD selected-fold run complete."
