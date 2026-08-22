#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/discover_witnesses_all_paired_hearings.py \
  --hearing-input data/processed/phase2/hearing_manifest.csv \
  --validated-hearing-input data/processed/phase2/hearing_manifest_validated.csv \
  --validated-witness-input data/processed/phase2/witness_manifest_validated.csv \
  --summary-input reports/phase2/trimodal_validation_summary.json \
  --output-csv data/processed/phase2/paired_hearing_witness_discovery.csv \
  "$@"

"$PYTHON_BIN" phase2/build_balanced_corpus_selection.py \
  --discovery-input data/processed/phase2/paired_hearing_witness_discovery.csv \
  --hearing-validated-input data/processed/phase2/hearing_manifest_validated.csv \
  --output-csv data/processed/phase2/trimodal_corpus_selection.csv \
  --summary-output reports/phase2/corpus_selection_summary.json \
  "$@"
