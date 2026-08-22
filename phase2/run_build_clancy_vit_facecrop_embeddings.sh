#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python}"
INPUT_CSV="${INPUT_CSV:?Set INPUT_CSV}"
OUTPUT_CSV="${OUTPUT_CSV:?Set OUTPUT_CSV}"
OUTPUT_ROOT="${OUTPUT_ROOT:?Set OUTPUT_ROOT}"
SUMMARY_JSON="${SUMMARY_JSON:?Set SUMMARY_JSON}"
DEVICE="${DEVICE:-cpu}"

export USE_TF="${USE_TF:-0}"
export TRANSFORMERS_NO_TF="${TRANSFORMERS_NO_TF:-1}"

"$PYTHON_BIN" phase2/build_clancy_vit_facecrop_embeddings.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --output-root "$OUTPUT_ROOT" \
  --summary-json "$SUMMARY_JSON" \
  --device "$DEVICE" \
  "$@"
