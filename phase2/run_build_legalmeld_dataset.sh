#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi
HEARING_MANIFEST="${HEARING_MANIFEST:-$ROOT_DIR/data/processed/phase2/hearing_manifest_validated.csv}"
MEDIA_MANIFEST="${MEDIA_MANIFEST:-$ROOT_DIR/data/phase2/ucr_case_video_strict/index/ucr_case_videos_strict.csv}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT_DIR/data/processed/phase2/legalmeld}"
MODEL_NAME="${MODEL_NAME:-tiny.en}"
ALIGNMENT_BACKEND="${ALIGNMENT_BACKEND:-auto}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/build_legalmeld_dataset.py" \
  --hearing-manifest "$HEARING_MANIFEST" \
  --media-manifest "$MEDIA_MANIFEST" \
  --output-root "$OUTPUT_ROOT" \
  --model-name "$MODEL_NAME" \
  --alignment-backend "$ALIGNMENT_BACKEND" \
  "$@"
