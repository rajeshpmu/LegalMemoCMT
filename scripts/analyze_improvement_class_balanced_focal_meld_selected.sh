#!/usr/bin/env bash
set -euo pipefail

# Analysis companion for the selected-fold MELD focal-loss improvement run.
# It exports predictions from the trained checkpoints and generates the same
# confusion/error analysis artifacts used in the earlier paper-aligned reports.

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="${MELD_RAW_MANIFEST:-data/manifests/meld_raw.csv}"
RESULTS_DIR="${RESULTS_DIR:-results/improvement/class_balanced_focal/meld_selected/cmt_min}"
MELD_CV_DIR="${MELD_CV_DIR:-data/manifests/meld_cv}"
SELECTED_FOLDS=(2 4)

for fold in "${SELECTED_FOLDS[@]}"; do
  fold_dir="${RESULTS_DIR}/fold_${fold}"
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

echo "Improvement MELD selected-fold analysis complete."
