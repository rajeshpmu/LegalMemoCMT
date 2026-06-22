#!/usr/bin/env bash
set -euo pipefail

# Paper-aligned CREMA-D analysis wrapper.
# This is the companion to scripts/run_paper_aligned_crema_d.sh.
# It exports held-out test predictions and generates the same analysis
# artefacts used for the MELD fold analysis:
# - predicted_vs_actual_first20.csv
# - predicted_vs_actual_first20.md
# - confusion_matrix.csv
# - top_confusions.csv
# - report.txt

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MANIFEST="${1:-data/manifests/crema_d.csv}"
CHECKPOINT="${2:-results/paper_aligned_crema_d/cmt_min/best_model.pt}"
OUTPUT_DIR="${3:-results/paper_aligned_crema_d/cmt_min/analysis_test}"

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

echo "Paper-aligned CREMA-D analysis complete."
