#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
DEVICE="${DEVICE:-auto}"

if [ "$DEVICE" = "auto" ] && command -v nvidia-smi >/dev/null 2>&1; then
  DEVICE="cuda"
fi

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
  --modalities text,audio,video \
  --fusion-pooling mean \
  --device "$DEVICE"
