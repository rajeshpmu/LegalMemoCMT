#!/usr/bin/env bash
set -euo pipefail

# Paper-exact MELD pooling sweep template.
#
# Intended for reproducing the paper's MELD fusion-mechanism comparison:
# CLS, MAX, MEAN, and MIN.
#
# Use this if you want a paper-style ablation table alongside the main
# paper-exact MELD CMT + MIN run.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="data/manifests/meld_raw.csv"
RESULTS_DIR="results/paper_exact_meld_sweep"

mkdir -p "$RESULTS_DIR"

"$PYTHON_BIN" scripts/build_meld_raw_manifest.py \
  --meld-root data/MELD \
  --manifest-dir data/manifests

run_one() {
  local tag="$1"
  local fusion_pooling="$2"
  local out_dir="${RESULTS_DIR}/${tag}"

  "$PYTHON_BIN" -m src.train.train \
    --manifest "$MELD_RAW_MANIFEST" \
    --train-split train \
    --val-split dev \
    --output-dir "$out_dir" \
    --encoder-mode paper \
    --fine-tune-backbones \
    --device cpu \
    --modalities "text,audio" \
    --loss-type weighted-ce \
    --fusion-pooling "$fusion_pooling" \
    --epochs 100 \
    --batch-size 4 \
    --lr 1e-4

  "$PYTHON_BIN" -m src.train.evaluate \
    --manifest "$MELD_RAW_MANIFEST" \
    --split test \
    --checkpoint "$out_dir/best_model.pt" \
    --output-json "$out_dir/metrics.json" \
    --output-predictions-csv "$out_dir/predictions_test.csv" \
    --encoder-mode paper \
    --device cpu \
    --modalities "text,audio" \
    --fusion-pooling "$fusion_pooling" \
    --batch-size 4
}

run_one "cmt_cls" "cls"
run_one "cmt_mean" "mean"
run_one "cmt_max" "max"
run_one "cmt_min" "min"

echo "Paper-exact MELD pooling sweep template complete."
