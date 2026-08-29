#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv-audio-ser/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Audio SER environment not found. Run phase2/annotation/setup_audio_ser.sh first." >&2
  exit 1
fi
exec "$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/run_audio_ser_evidence.py" "$@"
