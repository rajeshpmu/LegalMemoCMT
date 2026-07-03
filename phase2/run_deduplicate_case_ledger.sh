#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/deduplicate_case_ledger.py \
  --input-csv data/phase2/source_manifests/case_candidate_ledger.csv data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv data/phase2/source_manifests/tribunal_manifest_from_ledger.csv \
  --output-csv data/phase2/source_manifests/case_candidate_ledger_deduped.csv \
  "$@"
