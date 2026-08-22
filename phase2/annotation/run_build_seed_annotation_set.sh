#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/build_seed_annotation_set.py" "$@"
