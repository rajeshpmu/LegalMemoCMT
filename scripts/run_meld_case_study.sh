#!/usr/bin/env bash
set -euo pipefail

# Optional case study aligned with the base paper's MELD discussion.
# Runs only the MELD CMT variants so you can compare pooling choices.

mkdir -p results/meld_case_study

run_one() {
  local tag="$1"
  local fusion_pooling="$2"
  local out_dir="results/meld_case_study/${tag}"

  python3 -m src.train.train \
    --manifest data/manifests/meld_train.csv \
    --output-dir "$out_dir" \
    --modalities "text,audio" \
    --loss-type weighted-ce \
    --fusion-pooling "$fusion_pooling"
  python3 -m src.train.evaluate \
    --manifest data/manifests/meld_train.csv \
    --checkpoint "$out_dir/best_model.pt" \
    --output-json "$out_dir/metrics.json" \
    --modalities "text,audio" \
    --fusion-pooling "$fusion_pooling"
}

run_one "cmt_cls" "cls"
run_one "cmt_mean" "mean"
run_one "cmt_max" "max"
run_one "cmt_min" "min"

echo "MELD case study complete."
