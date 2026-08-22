#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/build_mict_hearings_candidate_manifest.py \
  --output-csv data/processed/phase2/mict_hearings_candidate_manifest.csv \
  --summary-json reports/phase2/mict_hearings_candidate_manifest_summary.json \
  "$@"
