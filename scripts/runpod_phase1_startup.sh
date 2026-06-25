#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

echo "RunPod Phase 1 startup sequence"
echo "Repository root: $ROOT_DIR"
echo

echo "1) Environment check"
"$PYTHON_BIN" - <<'PY'
import importlib
mods = [
    "torch",
    "numpy",
    "pandas",
]
for mod in mods:
    importlib.import_module(mod)
    print(f"OK {mod}")
PY

echo
echo "2) Smoke test"
"$PYTHON_BIN" "$ROOT_DIR/scripts/smoke_test.py"

echo
echo "3) MELD readiness check"
"$ROOT_DIR/scripts/check_phase1_meld_ready.sh"

echo
echo "4) MELD fold run order"
echo "a. Build MELD raw manifest and/or fold CSVs if missing."
echo "b. Run the paper-aligned MELD 5-fold CV script."
echo "c. Evaluate each saved best_model.pt checkpoint on the MELD test split."
echo "d. Export predictions and render confusion matrices."
echo "e. Aggregate the fold metrics and compare fold 2 versus fold 4."

echo
echo "Recommended next command after readiness passes:"
echo "bash scripts/run_paper_aligned_meld_cv.sh"

