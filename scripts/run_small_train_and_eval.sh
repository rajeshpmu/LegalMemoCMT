#!/usr/bin/env bash
set -euo pipefail

# Small-run training + evaluation wrapper.
# It creates a subset manifest, trains on it, then evaluates the saved checkpoint.

mkdir -p results/phase1_small_eval

run_one() {
  local name="$1"
  local full_manifest="$2"
  local subset_manifest="data/manifests/${name}_small.csv"
  local out_dir="results/phase1_small_eval/${name}"

  python3 scripts/create_subset_manifest.py --manifest "$full_manifest" --output "$subset_manifest" --per-split 100
  python3 -m src.train.train --manifest "$subset_manifest" --output-dir "$out_dir" --loss-type weighted-ce
  python3 -m src.train.evaluate --manifest "$subset_manifest" --checkpoint "$out_dir/best_model.pt" --output-json "$out_dir/metrics.json"
}

run_one "meld_train" "data/manifests/meld_train.csv"
run_one "crema_d" "data/manifests/crema_d.csv"

# IEMOCAP remains deferred.
