#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

TRIBUNAL_SOURCES="${TRIBUNAL_SOURCES:-data/phase2/source_manifests/tribunal_sources_target_dataset.csv}"
WITNESS_MANIFEST="${WITNESS_MANIFEST:-data/phase2/source_manifests/witness_harvest_manifest.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-data/processed/phase2/phase2_expanded_planning_manifest.csv}"

"$PYTHON_BIN" phase2/expand_phase2_planning_manifests.py \
  --tribunal-sources "$TRIBUNAL_SOURCES" \
  --witness-manifest "$WITNESS_MANIFEST" \
  --output-csv "$OUTPUT_CSV" \
  "$@"
