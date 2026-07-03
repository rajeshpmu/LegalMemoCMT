#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

MANIFEST="${MANIFEST:-data/manifests/meld_train.csv}"
PREDICTIONS_CSV="${PREDICTIONS_CSV:-results/paper_aligned_meld_cv/cmt_min/fold_2/predictions_test.csv}"
METRICS_JSON="${METRICS_JSON:-results/paper_aligned_meld_cv/cmt_min/fold_2/metrics.json}"
ANALYSIS_DIR="${ANALYSIS_DIR:-results/paper_aligned_meld_cv/cmt_min/fold_2/analysis_test}"
OUTPUT_DIR="${OUTPUT_DIR:-results/phase1_review_demo/fold2_baseline}"
MAX_EXAMPLES="${MAX_EXAMPLES:-5}"

if [ ! -f "$MANIFEST" ]; then
  echo "Missing manifest: $MANIFEST" >&2
  exit 1
fi
if [ ! -f "$PREDICTIONS_CSV" ]; then
  echo "Missing predictions CSV: $PREDICTIONS_CSV" >&2
  exit 1
fi
if [ ! -f "$METRICS_JSON" ]; then
  echo "Missing metrics JSON: $METRICS_JSON" >&2
  exit 1
fi
if [ ! -d "$ANALYSIS_DIR" ]; then
  echo "Missing analysis directory: $ANALYSIS_DIR" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/build_phase1_review_demo_bundle.py \
  --manifest "$MANIFEST" \
  --predictions-csv "$PREDICTIONS_CSV" \
  --metrics-json "$METRICS_JSON" \
  --analysis-dir "$ANALYSIS_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --max-examples "$MAX_EXAMPLES"

echo "Phase 1 demo bundle ready at $OUTPUT_DIR"
