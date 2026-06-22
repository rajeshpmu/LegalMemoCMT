#!/usr/bin/env bash
set -euo pipefail

# Analysis wrapper for the primary CREMA-D speech-emotion run.

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MANIFEST="${1:-data/manifests/crema_d.csv}"
CHECKPOINT="${2:-results/primary_speech_emotion/crema_d/cmt_min/best_model.pt}"
OUTPUT_DIR="${3:-results/primary_speech_emotion/crema_d/cmt_min/analysis_test}"

if [ ! -f "$MANIFEST" ]; then
  echo "Missing manifest: $MANIFEST" >&2
  exit 1
fi

if [ ! -f "$CHECKPOINT" ]; then
  echo "Missing checkpoint: $CHECKPOINT" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

"$PYTHON_BIN" -m src.tools.export_predictions \
  --manifest "$MANIFEST" \
  --split test \
  --checkpoint "$CHECKPOINT" \
  --output-csv "$OUTPUT_DIR/predictions_test.csv" \
  --batch-size 4 \
  --modalities "text,audio" \
  --fusion-pooling min \
  --encoder-mode paper \
  --device cpu

"$PYTHON_BIN" scripts/analyze_predictions.py \
  --predictions-csv "$OUTPUT_DIR/predictions_test.csv" \
  --output-dir "$OUTPUT_DIR" \
  --dataset crema_d

echo "Primary CREMA-D analysis complete."
