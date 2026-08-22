#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/build_text_only_diversity_supplement.py" \
  --hearing-input "$ROOT_DIR/data/processed/phase2/hearing_manifest_validated.csv" \
  --output-csv "$ROOT_DIR/data/processed/phase2/text_only_diversity_supplement.csv" \
  --summary-output "$ROOT_DIR/reports/phase2/text_only_diversity_supplement_summary.json"
