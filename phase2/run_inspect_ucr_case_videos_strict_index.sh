#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/inspect_ucr_case_videos_strict_index.py \
  --index-csv data/phase2/ucr_case_video_strict/index/ucr_case_videos_strict.csv \
  --source-csv data/processed/phase2/tap_candidate_manifest.csv \
  --output-dir data/phase2/ucr_case_video_strict/inspection \
  "$@"
