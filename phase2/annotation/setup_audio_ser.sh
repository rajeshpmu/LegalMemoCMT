#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_CREATE="${PYTHON_CREATE:-/usr/bin/python3}"
VENV_DIR="${AUDIO_SER_VENV:-$ROOT_DIR/.venv-audio-ser}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_CREATE" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$ROOT_DIR/requirements-phase2-audio-ser.txt"
echo "Audio SER environment ready: $VENV_DIR/bin/python"
