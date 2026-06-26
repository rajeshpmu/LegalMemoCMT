#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/expand_phase2_planning_manifests.py \
  --tribunal-sources data/phase2/source_manifests/tribunal_sources_target_dataset.csv \
  --witness-manifest data/phase2/source_manifests/witness_harvest_manifest.csv \
  --output-csv data/processed/phase2/phase2_expanded_planning_manifest.csv \
  "$@"
