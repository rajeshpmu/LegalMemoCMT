#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/enrich_case_ledger_from_ucr_site.py \
  --ledger-csv data/phase2/source_manifests/case_candidate_ledger.csv \
  --output-csv data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv \
  ${EXTRA_LEDGER_ARGS:-} \
  "$@"
