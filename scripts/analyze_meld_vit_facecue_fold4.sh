#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
OUTPUT_DIR="${OUTPUT_DIR:-results/facial_cues/meld_vit/fold_4}"
PRED_CSV="${PRED_CSV:-$OUTPUT_DIR/predictions_test.csv}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$OUTPUT_DIR/analysis_test}"
RAW_MANIFEST="${RAW_MANIFEST:-data/manifests/meld_vit_facecue.csv}"

mkdir -p "$ANALYSIS_DIR"
"$PYTHON_BIN" -m src.tools.export_predictions \
  --manifest "$RAW_MANIFEST" \
  --split test \
  --checkpoint "$OUTPUT_DIR/best_model.pt" \
  --output-csv "$PRED_CSV" \
  --batch-size 4 \
  --modalities "text,audio,video" \
  --fusion-pooling min \
  --encoder-mode paper \
  --device cpu

"$PYTHON_BIN" scripts/analyze_predictions.py \
  --predictions-csv "$PRED_CSV" \
  --output-dir "$ANALYSIS_DIR" \
  --dataset meld \
  --split test
