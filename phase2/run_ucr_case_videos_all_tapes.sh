#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${UCR_USERNAME:-}" || -z "${UCR_PASSWORD:-}" ]]; then
  echo "UCR_USERNAME and UCR_PASSWORD must be set before running this wrapper." >&2
  exit 1
fi

python3 phase2/download_ucr_case_videos_all_tapes.py \
  --source-csv data/phase2/source_manifests/tribunal_sources_target_dataset.csv \
  "$@"
