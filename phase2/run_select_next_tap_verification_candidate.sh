#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" phase2/select_next_tap_verification_candidate.py \
  --source-csv data/processed/phase2/tap_candidate_manifest.csv \
  --covered-map-csv data/phase2/ucr_case_video_strict/inspection/ucr_case_videos_strict_row_source_map.csv \
  --output-csv data/processed/phase2/next_tap_verification_manifest.csv \
  --summary-json reports/phase2/next_tap_verification_summary.json \
  "$@"
