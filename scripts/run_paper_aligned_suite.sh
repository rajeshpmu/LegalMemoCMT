#!/usr/bin/env bash
set -euo pipefail

# Paper-aligned MemoCMT-style suite.
# MELD now follows the paper-aligned 5-fold CV workflow with CMT + MIN.
# CREMA-D remains a separate benchmark with the same pretrained text/audio setup.

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

mkdir -p results/paper_aligned

bash scripts/run_paper_aligned_meld_cv.sh

run_one_crema() {
  local tag="$1"
  local modalities="$2"
  local fusion_pooling="${3:-mean}"
  local out_dir="results/paper_aligned/crema_${tag}"

  "$PYTHON_BIN" -m src.train.train \
    --manifest data/manifests/crema_d.csv \
    --train-split train \
    --val-split val \
    --output-dir "$out_dir" \
    --encoder-mode pretrained \
    --device cpu \
    --modalities "$modalities" \
    --loss-type weighted-ce \
    --fusion-pooling "$fusion_pooling" \
    --epochs 5 \
    --batch-size 4 \
    --lr 1e-4

  "$PYTHON_BIN" -m src.train.evaluate \
    --manifest data/manifests/crema_d.csv \
    --split test \
    --checkpoint "$out_dir/best_model.pt" \
    --output-json "$out_dir/metrics.json" \
    --encoder-mode pretrained \
    --device cpu \
    --modalities "$modalities" \
    --fusion-pooling "$fusion_pooling" \
    --batch-size 4
}

# SER: speech only
run_one_crema "ser_audio" "audio"

# TER: text only
run_one_crema "ter_text" "text"

# CMT: text + audio fusion variants
run_one_crema "cmt_cls" "text,audio" "cls"
run_one_crema "cmt_mean" "text,audio" "mean"
run_one_crema "cmt_max" "text,audio" "max"
run_one_crema "cmt_min" "text,audio" "min"

echo "Paper-aligned MemoCMT suite complete."
