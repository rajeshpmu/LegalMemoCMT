#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/build_ucr_case_inventory.py \
  --source-csv data/phase2/source_manifests/tribunal_sources_target_dataset.csv \
  --output-csv data/processed/phase2/ucr_case_inventory.csv \
  "$@"
