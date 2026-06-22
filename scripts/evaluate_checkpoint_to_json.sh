#!/usr/bin/env bash
set -euo pipefail

# Mandatory helper for saving metrics in machine-readable form.

if [ $# -lt 3 ]; then
  echo "Usage: $0 <manifest.csv> <checkpoint.pt> <output.json> [batch_size]" >&2
  exit 1
fi

MANIFEST="$1"
CHECKPOINT="$2"
OUTPUT_JSON="$3"
BATCH_SIZE="${4:-8}"

python3 -m src.train.evaluate --manifest "$MANIFEST" --checkpoint "$CHECKPOINT" --batch-size "$BATCH_SIZE" --output-json "$OUTPUT_JSON"
