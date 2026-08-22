#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/validate_trimodal_hearings.py \
  --hearing-input data/processed/phase2/hearing_manifest.csv \
  --hearing-output data/processed/phase2/hearing_manifest_validated.csv \
  --summary-output reports/phase2/trimodal_validation_summary.json \
  "$@"

"$PYTHON_BIN" phase2/resolve_witnesses_from_transcripts.py \
  --hearing-input data/processed/phase2/hearing_manifest_validated.csv \
  --witness-output data/processed/phase2/witness_manifest_validated.csv

"$PYTHON_BIN" phase2/estimate_utterance_counts.py \
  --witness-input data/processed/phase2/witness_manifest_validated.csv \
  --witness-output data/processed/phase2/witness_manifest_validated.csv \
  --summary-output reports/phase2/trimodal_validation_summary.json
