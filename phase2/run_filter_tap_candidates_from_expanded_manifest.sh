#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/filter_tap_candidates_from_expanded_manifest.py \
  --input-csv data/processed/phase2/phase2_expanded_planning_manifest.csv \
  --output-csv data/processed/phase2/tap_candidate_manifest.csv \
  --summary-json reports/phase2/tap_candidate_manifest_summary.json \
  "$@"
