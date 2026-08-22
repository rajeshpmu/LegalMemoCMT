#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 phase2/filter_tribunal_video_bearing_candidates.py \
  --source-csv data/processed/phase2/tribunal_media_discovery.csv \
  --output-csv data/processed/phase2/tribunal_video_bearing_candidates.csv \
  --summary-json reports/phase2/tribunal_video_bearing_candidates_summary.json \
  "$@"
