#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/build_broadened_tribunal_source_manifest.py \
  --base-manifest data/phase2/source_manifests/tribunal_sources_target_dataset.csv \
  --review-csv data/processed/phase2/tribunal_source_broadening_review.csv \
  --verified-additions-csv data/phase2/source_manifests/verified_tap_case_additions.csv \
  --output-csv data/phase2/source_manifests/tribunal_sources_target_dataset_broadened.csv \
  --include-hold-for-link-validation \
  "$@"
