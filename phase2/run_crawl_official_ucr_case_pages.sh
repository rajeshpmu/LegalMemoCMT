#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/crawl_official_ucr_case_pages.py \
  --seed-csv data/phase2/source_manifests/official_ucr_case_seeds.csv \
  --output-csv data/phase2/source_manifests/official_ucr_case_candidates.csv \
  "$@"
