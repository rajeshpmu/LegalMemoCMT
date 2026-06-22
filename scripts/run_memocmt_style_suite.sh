#!/usr/bin/env bash
set -euo pipefail

# Optional experimental suite that mirrors the MemoCMT paper structure.
# Runs SER, TER, and CMT fusion variants on MELD and CREMA-D.

mkdir -p results/memocmt_style

run_one() {
  local tag="$1"
  local manifest="$2"
  local modalities="$3"
  local loss_type="$4"
  local fusion_pooling="${5:-mean}"
  local out_dir="results/memocmt_style/${tag}"

  python3 -m src.train.train \
    --manifest "$manifest" \
    --output-dir "$out_dir" \
    --modalities "$modalities" \
    --loss-type "$loss_type" \
    --fusion-pooling "$fusion_pooling"
  python3 -m src.train.evaluate \
    --manifest "$manifest" \
    --checkpoint "$out_dir/best_model.pt" \
    --output-json "$out_dir/metrics.json" \
    --modalities "$modalities" \
    --fusion-pooling "$fusion_pooling"
}

run_one "meld_ser_audio" "data/manifests/meld_train.csv" "audio" "weighted-ce"
run_one "meld_ter_text" "data/manifests/meld_train.csv" "text" "weighted-ce"
run_one "meld_cmt_cls" "data/manifests/meld_train.csv" "text,audio" "weighted-ce" "cls"
run_one "meld_cmt_mean" "data/manifests/meld_train.csv" "text,audio" "weighted-ce" "mean"
run_one "meld_cmt_max" "data/manifests/meld_train.csv" "text,audio" "weighted-ce" "max"
run_one "meld_cmt_min" "data/manifests/meld_train.csv" "text,audio" "weighted-ce" "min"

run_one "crema_ser_audio" "data/manifests/crema_d.csv" "audio" "weighted-ce"
run_one "crema_ter_text" "data/manifests/crema_d.csv" "text" "weighted-ce"
run_one "crema_cmt_cls" "data/manifests/crema_d.csv" "text,audio" "weighted-ce" "cls"
run_one "crema_cmt_mean" "data/manifests/crema_d.csv" "text,audio" "weighted-ce" "mean"
run_one "crema_cmt_max" "data/manifests/crema_d.csv" "text,audio" "weighted-ce" "max"
run_one "crema_cmt_min" "data/manifests/crema_d.csv" "text,audio" "weighted-ce" "min"

echo "MemoCMT-style experiment suite complete."
