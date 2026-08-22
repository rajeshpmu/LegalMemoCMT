#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/discover_tribunal_media_candidates.py \
  --source-csv data/processed/phase2/expanded_planning_missing_sources.csv \
  --ledger-csv data/phase2/source_manifests/case_candidate_ledger.csv \
  --output-csv data/processed/phase2/tribunal_media_discovery.csv \
  --summary-json reports/phase2/tribunal_media_discovery_summary.json \
  "$@"
