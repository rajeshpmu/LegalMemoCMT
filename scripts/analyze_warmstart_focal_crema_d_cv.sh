#!/usr/bin/env bash
set -euo pipefail

# Analysis companion for the warm-start CREMA-D focal-loss CV run.
# Exports predictions from each fold checkpoint and generates confusion
# and error analysis artifacts for each validation fold.

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
OUTPUT_DIR="${OUTPUT_DIR:-results/improvement/warmstart_focal/crema_d_cv/cmt_min}"
CV_DIR="${CV_DIR:-data/manifests/crema_d_cv}"

for fold in 0 1 2 3 4; do
  fold_dir="${OUTPUT_DIR}/fold_${fold}"
  checkpoint="${fold_dir}/best_model.pt"
  val_manifest="${CV_DIR}/crema_d_fold_${fold}_val.csv"
  predictions_csv="${fold_dir}/analysis_val/predictions_val.csv"
  analysis_dir="${fold_dir}/analysis_val"

  if [ ! -f "$checkpoint" ]; then
    echo "Missing checkpoint: $checkpoint" >&2
    exit 1
  fi
  if [ ! -f "$val_manifest" ]; then
    echo "Missing validation manifest: $val_manifest" >&2
    exit 1
  fi

  mkdir -p "$analysis_dir"

  "$PYTHON_BIN" -m src.tools.export_predictions \
    --manifest "$val_manifest" \
    --split val \
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
    --dataset crema_d \
    --split val
done

echo "Warm-start focal-loss CREMA-D analysis complete."
