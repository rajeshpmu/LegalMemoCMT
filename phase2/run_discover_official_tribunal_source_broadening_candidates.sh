#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/discover_official_tribunal_source_broadening_candidates.py \
  --source-manifest data/phase2/source_manifests/tribunal_sources_target_dataset.csv \
  --output-csv data/processed/phase2/tribunal_source_broadening_review.csv \
  --summary-json reports/phase2/tribunal_source_broadening_review_summary.json \
  "$@"

