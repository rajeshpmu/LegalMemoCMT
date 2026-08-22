#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_dataset_manifest.csv}"
LABELS_CSV="${LABELS_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_weak_labels.csv}"
TRAINING_CSV="${TRAINING_CSV:-$ROOT_DIR/data/processed/phase2/clancy/clancy_training_manifest_weak.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_weak_label_summary.json}"
REVIEW_CSV="${REVIEW_CSV:-$ROOT_DIR/reports/phase2/clancy_weak_label_review.csv}"

"$PYTHON_BIN" phase2/build_clancy_weak_labels.py \
  --input-csv "$INPUT_CSV" \
  --labels-csv "$LABELS_CSV" \
  --training-csv "$TRAINING_CSV" \
  --summary-json "$SUMMARY_JSON" \
  --review-csv "$REVIEW_CSV" \
  "$@"
