#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/build_ucr_case_inventory.py \
  --source-csv data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv \
  --output-csv data/processed/phase2/verified_case_inventory.csv \
  "$@"
