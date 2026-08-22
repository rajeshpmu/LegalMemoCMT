#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/build_hearing_manifest.py \
  --inventory-csv data/processed/phase2/verified_case_inventory.csv \
  --video-manifest-csv data/processed/phase2/ucr_video_candidate_manifest.csv \
  --transcript-manifest-csv data/processed/phase2/ucr_transcript_only_manifest.csv \
  --output-csv data/processed/phase2/hearing_manifest.csv \
  --summary-json reports/phase2/hearing_witness_manifest_summary.json \
  "$@"

"$PYTHON_BIN" phase2/build_witness_manifest.py \
  --hearing-manifest-csv data/processed/phase2/hearing_manifest.csv \
  --output-csv data/phase2/source_manifests/witness_harvest_manifest_resolved.csv
