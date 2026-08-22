#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/compare_expanded_planning_to_verified_inventory.py \
  --expanded-csv data/processed/phase2/phase2_expanded_planning_manifest.csv \
  --inventory-csv data/processed/phase2/verified_case_inventory.csv \
  --output-csv data/processed/phase2/expanded_planning_vs_verified_inventory.csv \
  --missing-csv data/processed/phase2/expanded_planning_missing_sources.csv \
  --summary-json reports/phase2/expanded_planning_vs_verified_inventory_summary.json \
  "$@"
