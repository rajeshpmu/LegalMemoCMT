#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/legalai-py311/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
fi

PAIRS_CSV="${1:-}"

if [ -z "$PAIRS_CSV" ]; then
  echo "Usage: bash scripts/run_phase1_raw_mp4_demo_batch.sh <pairs.csv>" >&2
  echo "pairs.csv must contain columns: sample_id,video_path" >&2
  exit 1
fi

if [ ! -f "$PAIRS_CSV" ]; then
  echo "Missing pairs CSV: $PAIRS_CSV" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/run_phase1_raw_mp4_demo_batch.py --pairs-csv "$PAIRS_CSV"
