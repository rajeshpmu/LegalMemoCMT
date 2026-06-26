#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/build_scotus_text_manifest.py \
  --input-csv data/phase2/scotus/index/scotus_transcripts.csv \
  --output-csv data/processed/phase2/scotus_text_manifest.csv \
  "$@"
