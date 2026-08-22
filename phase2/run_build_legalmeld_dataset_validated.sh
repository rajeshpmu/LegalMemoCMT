#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi
HEARING_MANIFEST="${HEARING_MANIFEST:-$ROOT_DIR/data/processed/phase2/hearing_manifest_validated.csv}"
MEDIA_MANIFEST="${MEDIA_MANIFEST:-$ROOT_DIR/data/phase2/ucr_case_video_strict/index/ucr_case_videos_strict.csv}"
SELECTION_MANIFEST="${SELECTION_MANIFEST:-$ROOT_DIR/data/processed/phase2/trimodal_corpus_selection.csv}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT_DIR/data/processed/phase2/legalmeld_validated}"
MODEL_NAME="${MODEL_NAME:-tiny.en}"
MAX_HEARINGS="${MAX_HEARINGS:-5}"
MAX_UTTERANCES="${MAX_UTTERANCES:-40}"
ALIGNMENT_BACKEND="${ALIGNMENT_BACKEND:-auto}"
INCLUDE_HEARING_IDS="${INCLUDE_HEARING_IDS:-hear_c149355188328b0b}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/build_legalmeld_dataset.py" \
  --hearing-manifest "$HEARING_MANIFEST" \
  --media-manifest "$MEDIA_MANIFEST" \
  --selection-manifest "$SELECTION_MANIFEST" \
  --include-hearing-ids "$INCLUDE_HEARING_IDS" \
  --output-root "$OUTPUT_ROOT" \
  --model-name "$MODEL_NAME" \
  --max-hearings "$MAX_HEARINGS" \
  --max-utterances "$MAX_UTTERANCES" \
  --alignment-backend "$ALIGNMENT_BACKEND" \
  "$@"
