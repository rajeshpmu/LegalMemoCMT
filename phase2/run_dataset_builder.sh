#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <command> [args...]" >&2
  echo "Commands: validate-tri, validate-witness, resolve, download-transcript, download-video, extract-audio, segment, build-dataset, weak-labels, dashboard" >&2
  exit 1
fi

"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" "$@"
