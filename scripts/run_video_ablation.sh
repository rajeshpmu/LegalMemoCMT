#!/usr/bin/env bash
set -euo pipefail

# Video ablation only.
# This script keeps video out of the paper-aligned core path and evaluates it separately.
# It is intended for optional analysis, not the main MemoCMT-style comparison.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

mkdir -p results/video_ablation

run_one() {
  local dataset_name="$1"
  local manifest="$2"
  local out_dir="results/video_ablation/${dataset_name}"

  "$PYTHON_BIN" -m src.train.train \
    --manifest "$manifest" \
    --output-dir "$out_dir" \
    --encoder-mode legacy \
    --device cpu \
    --modalities "video" \
    --loss-type weighted-ce \
    --fusion-pooling mean \
    --epochs 5 \
    --batch-size 4 \
    --lr 1e-4

  "$PYTHON_BIN" -m src.train.evaluate \
    --manifest "$manifest" \
    --checkpoint "$out_dir/best_model.pt" \
    --output-json "$out_dir/metrics.json" \
    --encoder-mode legacy \
    --device cpu \
    --modalities "video" \
    --fusion-pooling mean \
    --batch-size 4
}

run_one "meld" "data/manifests/meld_raw.csv"
run_one "crema_d" "data/manifests/crema_d.csv"

echo "Video ablation complete."
