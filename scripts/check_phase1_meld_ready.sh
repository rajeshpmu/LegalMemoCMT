#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

MANIFESTS=("$@")
if [ "${#MANIFESTS[@]}" -eq 0 ]; then
  MANIFESTS=(
    "$ROOT_DIR/data/manifests/meld_train.csv"
    "$ROOT_DIR/data/manifests/meld_dev.csv"
    "$ROOT_DIR/data/manifests/meld_test.csv"
    "$ROOT_DIR/data/manifests/meld_raw.csv"
  )
fi

echo "Phase 1 MELD readiness check"
echo "Repository root: $ROOT_DIR"
echo

echo "1) Environment probe"
"$PYTHON_BIN" - <<'PY'
import importlib
mods = [
    "torch",
    "numpy",
    "pandas",
]
for mod in mods:
    try:
        importlib.import_module(mod)
        print(f"OK {mod}")
    except Exception as exc:
        print(f"FAIL {mod}: {exc}")
        raise SystemExit(1)
PY

echo
echo "2) Manifest asset checks"
for manifest in "${MANIFESTS[@]}"; do
  if [ ! -f "$manifest" ]; then
    echo "Missing manifest: $manifest"
    continue
  fi
  echo "--- $manifest"
  "$PYTHON_BIN" "$ROOT_DIR/scripts/check_manifest_assets.py" --manifest "$manifest" --max-samples 2
  echo
done

echo "If every manifest check reports all required files present, the raw MELD archive is not needed for that specific manifest."

