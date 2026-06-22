#!/usr/bin/env bash
set -euo pipefail

# Held-out prediction export built on top of the working evaluation module.

if [ $# -lt 4 ]; then
  echo "Usage: $0 <manifest.csv> <checkpoint.pt> <output-predictions.csv> <split> [batch_size]" >&2
  exit 1
fi

MANIFEST="$1"
CHECKPOINT="$2"
OUTPUT_PREDICTIONS="$3"
SPLIT="$4"
BATCH_SIZE="${5:-8}"

python3 -m src.tools.export_predictions \
  --manifest "$MANIFEST" \
  --split "$SPLIT" \
  --checkpoint "$CHECKPOINT" \
  --batch-size "$BATCH_SIZE" \
  --output-csv "$OUTPUT_PREDICTIONS"
