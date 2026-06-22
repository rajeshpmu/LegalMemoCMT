#!/usr/bin/env bash
set -euo pipefail

# Analysis wrapper for the primary conversational MELD track.
# Defaults to fold 2 because it was a strong representative fold in the
# earlier MELD CV analysis, but any fold can be passed explicitly.

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
FOLD="${1:-2}"
RESULTS_DIR="${2:-results/primary_conversational/meld_cv/cmt_min}"
PREDICTIONS_CSV="${RESULTS_DIR}/fold_${FOLD}/predictions_test.csv"
OUTPUT_DIR="${3:-${RESULTS_DIR}/fold_${FOLD}/analysis_test}"

if [ ! -f "$PREDICTIONS_CSV" ]; then
  echo "Missing predictions file: $PREDICTIONS_CSV" >&2
  echo "Run scripts/run_primary_conversational_meld_cv.sh first." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

"$PYTHON_BIN" scripts/analyze_predictions.py \
  --predictions-csv "$PREDICTIONS_CSV" \
  --output-dir "$OUTPUT_DIR" \
  --dataset meld

echo "Primary conversational MELD analysis complete for fold $FOLD."
