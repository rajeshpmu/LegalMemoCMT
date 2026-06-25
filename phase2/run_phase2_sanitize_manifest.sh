#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_clean.csv}"
EXTRACT_AUDIO_FROM_VIDEO="${EXTRACT_AUDIO_FROM_VIDEO:-1}"
REQUIRE_AUDIO="${REQUIRE_AUDIO:-0}"
REQUIRE_VIDEO="${REQUIRE_VIDEO:-0}"

ARGS=(--input-csv "$INPUT_CSV" --output-csv "$OUTPUT_CSV")

if [ "$EXTRACT_AUDIO_FROM_VIDEO" = "1" ]; then
  ARGS+=(--extract-audio-from-video)
fi
if [ "$REQUIRE_AUDIO" = "1" ]; then
  ARGS+=(--require-audio)
fi
if [ "$REQUIRE_VIDEO" = "1" ]; then
  ARGS+=(--require-video)
fi

"$PYTHON_BIN" "$ROOT_DIR/phase2/sanitize_phase2_manifest.py" "${ARGS[@]}" "$@"
