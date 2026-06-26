#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/split_ucr_inventory_by_media_type.py \
  --inventory-csv data/processed/phase2/ucr_case_inventory.csv \
  --video-output-csv data/processed/phase2/ucr_video_candidate_manifest.csv \
  --transcript-output-csv data/processed/phase2/ucr_transcript_only_manifest.csv \
  "$@"
