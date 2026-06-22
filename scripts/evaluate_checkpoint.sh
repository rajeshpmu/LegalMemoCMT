#!/usr/bin/env bash
set -euo pipefail

# Mandatory after every successful training run.
# Evaluates a saved checkpoint on the provided manifest.

if [ $# -lt 2 ]; then
  echo "Usage: $0 <manifest.csv> <checkpoint.pt> [batch_size]" >&2
  exit 1
fi

MANIFEST="$1"
CHECKPOINT="$2"
BATCH_SIZE="${3:-8}"

python3 -m src.train.evaluate --manifest "$MANIFEST" --checkpoint "$CHECKPOINT" --batch-size "$BATCH_SIZE"
