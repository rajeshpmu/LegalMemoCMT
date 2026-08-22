#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

URLS_FILE="${URLS_FILE:-$ROOT_DIR/data/clancy_urls.txt}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_source_manifest.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_source_manifest_summary.json}"
YTDLP_BIN="${YTDLP_BIN:-yt-dlp}"
COOKIES_FROM_BROWSER="${COOKIES_FROM_BROWSER-}"
COOKIES_FILE="${COOKIES_FILE:-}"
JS_RUNTIMES="${JS_RUNTIMES:-}"

"$PYTHON_BIN" phase2/build_clancy_source_manifest.py \
  --urls-file "$URLS_FILE" \
  --output-csv "$OUTPUT_CSV" \
  --summary-json "$SUMMARY_JSON" \
  --ytdlp-bin "$YTDLP_BIN" \
  --cookies-from-browser "$COOKIES_FROM_BROWSER" \
  --cookies-file "$COOKIES_FILE" \
  --js-runtimes "$JS_RUNTIMES" \
  "$@"
