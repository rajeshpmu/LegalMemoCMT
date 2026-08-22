#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/resolve_targeted_tribunal_case_numbers.py \
  --source-csv data/processed/phase2/tribunal_media_discovery.csv \
  --output-csv data/processed/phase2/tribunal_case_resolution_review.csv \
  --summary-json reports/phase2/tribunal_case_resolution_review_summary.json \
  "$@"
