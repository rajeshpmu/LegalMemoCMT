#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
INPUT_CSV="${1:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_clean.csv}"
OUTPUT_CSV="${2:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_tri_modal.csv}"
AUDIO_OUTPUT_DIR="${AUDIO_OUTPUT_DIR:-$ROOT_DIR/data/processed/phase2/extracted_audio}"

if [ ! -f "$INPUT_CSV" ]; then
  echo "Missing Phase 2 manifest for audio extraction: $INPUT_CSV" >&2
  exit 1
fi

echo "Phase 2 audio extraction stage"
echo "Input manifest: $INPUT_CSV"
echo "Output manifest: $OUTPUT_CSV"
echo "Audio output dir: $AUDIO_OUTPUT_DIR"
echo

"$PYTHON_BIN" "$ROOT_DIR/phase2/sanitize_phase2_manifest.py" \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --extract-audio-from-video \
  --audio-output-dir "$AUDIO_OUTPUT_DIR" \
  --require-video \
  "$@"

echo
echo "Phase 2 audio extraction stage complete."
