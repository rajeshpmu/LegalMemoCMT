#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper for the first improvement step.
# Runs the selected-fold MELD focal-loss workflow and then the CREMA-D
# focal-loss CV workflow sequentially.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/run_improvement_class_balanced_focal_meld_selected.sh"
"$SCRIPT_DIR/analyze_improvement_class_balanced_focal_meld_selected.sh"
"$SCRIPT_DIR/run_improvement_class_balanced_focal_crema_d_cv.sh"
"$SCRIPT_DIR/analyze_improvement_class_balanced_focal_crema_d_cv.sh"

echo "Improvement focal-loss suite complete."
