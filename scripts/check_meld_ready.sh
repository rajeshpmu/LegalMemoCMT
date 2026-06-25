#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <manifest.csv> [--fail-on-missing]" >&2
  exit 1
fi

MANIFEST="$1"
shift || true

"$PYTHON_BIN" "$ROOT_DIR/scripts/check_manifest_assets.py" \
  --manifest "$MANIFEST" \
  "$@"

