#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <manifest.csv> <checkpoint.pt> <output.json> [split]" >&2
  exit 1
fi

MANIFEST="$1"
CHECKPOINT="$2"
OUTPUT_JSON="$3"
SPLIT="${4:-test}"

"$PYTHON_BIN" -m src.train.evaluate \
  --manifest "$MANIFEST" \
  --checkpoint "$CHECKPOINT" \
  --split "$SPLIT" \
  --output-json "$OUTPUT_JSON" \
  --encoder-mode paper \
  --modalities text,audio \
  --fusion-pooling mean \
  --device auto

