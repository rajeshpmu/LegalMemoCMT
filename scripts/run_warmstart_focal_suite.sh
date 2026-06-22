#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper for the warm-start focal-loss improvement path.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/run_warmstart_focal_meld_selected.sh"
"$SCRIPT_DIR/analyze_warmstart_focal_meld_selected.sh"
"$SCRIPT_DIR/run_warmstart_focal_crema_d_cv.sh"
"$SCRIPT_DIR/analyze_warmstart_focal_crema_d_cv.sh"

echo "Warm-start focal-loss suite complete."
