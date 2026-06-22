#!/usr/bin/env bash
set -euo pipefail

# Mandatory Phase 1 workflow for the current project state.
# Runs both benchmark small-train/eval cycles, saves JSON metrics, and compares them.

mkdir -p results/phase1_small_eval

echo "Step 1/3: Small train + evaluate for MELD and CREMA-D"
bash scripts/run_small_train_and_eval.sh

echo "Step 2/3: Compare benchmark metrics"
python3 scripts/compare_benchmarks.py \
  --meld-metrics results/phase1_small_eval/meld_train/metrics.json \
  --crema-metrics results/phase1_small_eval/crema_d/metrics.json

echo "Step 3/3: Mandatory Phase 1 checkpoint complete"
echo "Next actions are optional: tuning, full benchmark, or ablations."
