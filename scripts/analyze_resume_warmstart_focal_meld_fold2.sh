#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
OUTPUT_DIR="${OUTPUT_DIR:-results/improvement/warmresume_focal/meld_fold_2}"

if [ ! -f "$OUTPUT_DIR/metrics.json" ]; then
  echo "Missing metrics file: $OUTPUT_DIR/metrics.json" >&2
  exit 1
fi

if [ ! -f "$OUTPUT_DIR/predictions_test.csv" ]; then
  echo "Missing predictions file: $OUTPUT_DIR/predictions_test.csv" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/analyze_predictions.py \
  --predictions-csv "$OUTPUT_DIR/predictions_test.csv" \
  --output-dir "$OUTPUT_DIR/analysis_test" \
  --dataset meld \
  --split test

echo "Warm-resume Fold 2 analysis complete."
