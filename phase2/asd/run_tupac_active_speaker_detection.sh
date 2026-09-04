#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_witness_speaking_visual_review.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_witness_speaking_asd.csv}"
TRACKS_CSV="${TRACKS_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_asd_face_tracks.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/tupac_active_speaker_detection.json}"

"$PYTHON_BIN" phase2/asd/run_active_speaker_detection.py \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --tracks-csv "$TRACKS_CSV" \
  --summary-json "$SUMMARY_JSON" \
  "$@"
