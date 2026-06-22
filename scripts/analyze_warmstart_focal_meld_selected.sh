#!/usr/bin/env bash
set -euo pipefail

# Analysis companion for the warm-start MELD focal-loss run.
# Exports predictions for the selected folds and generates the same
# error-analysis artifacts used in the earlier MELD reports.

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="${MELD_RAW_MANIFEST:-data/manifests/meld_raw.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-results/improvement/warmstart_focal/meld_selected/cmt_min}"
SELECTED_FOLDS=(2 4)

for fold in "${SELECTED_FOLDS[@]}"; do
  fold_dir="${OUTPUT_DIR}/fold_${fold}"
  checkpoint="${fold_dir}/best_model.pt"
  predictions_csv="${fold_dir}/analysis_test/predictions_test.csv"
  analysis_dir="${fold_dir}/analysis_test"

  if [ ! -f "$checkpoint" ]; then
    echo "Missing checkpoint: $checkpoint" >&2
    exit 1
  fi

  mkdir -p "$analysis_dir"

  "$PYTHON_BIN" -m src.tools.export_predictions \
    --manifest "$MELD_RAW_MANIFEST" \
    --split test \
    --checkpoint "$checkpoint" \
    --output-csv "$predictions_csv" \
    --batch-size 4 \
    --modalities "text,audio" \
    --fusion-pooling min \
    --encoder-mode paper \
    --device cpu

  "$PYTHON_BIN" scripts/analyze_predictions.py \
    --predictions-csv "$predictions_csv" \
    --output-dir "$analysis_dir" \
    --dataset meld \
    --split test
done

echo "Warm-start focal-loss MELD analysis complete."
