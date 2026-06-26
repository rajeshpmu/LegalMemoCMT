#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/build_tribunal_manifest_from_ledger.py \
  --ledger-csv data/phase2/source_manifests/case_candidate_ledger.csv \
  --output-csv data/phase2/source_manifests/tribunal_manifest_from_ledger.csv \
  "$@"
