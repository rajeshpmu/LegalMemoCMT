#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

URLS_FILE="${URLS_FILE:-$ROOT_DIR/data/clancy_urls.txt}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT_DIR/data/phase2/clancy/corpus}"
MANIFEST_CSV="${MANIFEST_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_corpus_manifest.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_corpus_summary.json}"
if [[ -n "${YTDLP_BIN:-}" ]]; then
  YTDLP_BIN="$YTDLP_BIN"
elif [[ -x "$ROOT_DIR/.venv/bin/yt-dlp" ]]; then
  YTDLP_BIN="$ROOT_DIR/.venv/bin/yt-dlp"
else
  YTDLP_BIN="$(command -v yt-dlp || true)"
fi
if [[ -z "$YTDLP_BIN" ]]; then
  echo "yt-dlp not found. Install it with: $PYTHON_BIN -m pip install -U yt-dlp" >&2
  exit 1
fi
FFMPEG_BIN="${FFMPEG_BIN:-ffmpeg}"
COOKIES_FILE="${COOKIES_FILE:-}"
JS_RUNTIMES="${JS_RUNTIMES:-}"
if [[ -n "${COOKIES_FROM_BROWSER+x}" ]]; then
  COOKIES_FROM_BROWSER="$COOKIES_FROM_BROWSER"
elif [[ -d "$HOME/.config/google-chrome" || -d "$HOME/.config/chromium" ]]; then
  COOKIES_FROM_BROWSER="chrome"
else
  COOKIES_FROM_BROWSER=""
fi
FORMAT_STRING="${FORMAT_STRING:-137+140/bestvideo*+bestaudio/best}"
SUBTITLE_LANGS="${SUBTITLE_LANGS:-en}"

"$PYTHON_BIN" phase2/build_clancy_corpus.py \
  --urls-file "$URLS_FILE" \
  --output-root "$OUTPUT_ROOT" \
  --manifest-csv "$MANIFEST_CSV" \
  --summary-json "$SUMMARY_JSON" \
  --ytdlp-bin "$YTDLP_BIN" \
  --ffmpeg-bin "$FFMPEG_BIN" \
  --cookies-from-browser "$COOKIES_FROM_BROWSER" \
  --cookies-file "$COOKIES_FILE" \
  --js-runtimes "$JS_RUNTIMES" \
  --format-string "$FORMAT_STRING" \
  --subtitle-langs "$SUBTITLE_LANGS" \
  "$@"
