#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_training_manifest_weak.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_training_readiness_summary.json}"
ISSUES_CSV="${ISSUES_CSV:-$ROOT_DIR/reports/phase2/clancy_training_readiness_issues.csv}"

"$PYTHON_BIN" phase2/build_clancy_training_readiness.py \
  --input-csv "$INPUT_CSV" \
  --summary-json "$SUMMARY_JSON" \
  --issues-csv "$ISSUES_CSV" \
  "$@"
