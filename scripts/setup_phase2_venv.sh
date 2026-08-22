#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
REQ_FILE="${REQ_FILE:-$ROOT_DIR/requirements-phase2.txt}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "No usable python3 found on PATH" >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "Failed to create venv at $VENV_DIR" >&2
  exit 1
fi

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -r "$REQ_FILE"

cat <<EOF
Phase 2 venv ready:
  $VENV_PYTHON

Use it with:
  source "$VENV_DIR/bin/activate"
  python3 phase2/run_build_legalmeld_dataset_validated.sh --skip-existing
EOF
