#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/build_witness_controlled_validation_manual_review.py" \
  --input-csv "$ROOT_DIR/data/processed/phase2/legalmeld_validated/witness_only_rows/witness_controlled_validation_subset.csv" \
  --output-csv "$ROOT_DIR/data/processed/phase2/legalmeld_validated/witness_only_rows/witness_controlled_validation_manual_review.csv" \
  --summary-json "$ROOT_DIR/reports/phase2/witness_controlled_validation_manual_review_summary.json" \
  "$@"
