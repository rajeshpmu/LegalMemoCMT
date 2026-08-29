#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
ORIGINAL_CSV="${ORIGINAL_CSV:-$ROOT_DIR/data/processed/phase2/clancy/emotion_scope_review_200_scope_aware.csv}"
DEBERTA_CSV="${DEBERTA_CSV:-$ROOT_DIR/data/processed/phase2/clancy/emotion_scope_review_200_deberta.csv}"
COMPARISON_CSV="${COMPARISON_CSV:-$ROOT_DIR/data/processed/phase2/clancy/emotion_scope_review_200_deberta_comparison.csv}"
DISAGREEMENTS_CSV="${DISAGREEMENTS_CSV:-$ROOT_DIR/data/processed/phase2/clancy/emotion_scope_review_200_deberta_disagreements.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/clancy_emotion_scope_review_200_deberta_comparison.json}"
REVIEW_CSV="${REVIEW_CSV:-$ROOT_DIR/data/processed/phase2/clancy/emotion_scope_review_200_deberta_stratified_review.csv}"
REVIEW_SUMMARY="${REVIEW_SUMMARY:-$ROOT_DIR/reports/phase2/clancy_emotion_scope_review_200_deberta_stratified_review.json}"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/compare_deberta_scope_predictions.py" \
  --original-csv "$ORIGINAL_CSV" \
  --deberta-csv "$DEBERTA_CSV" \
  --output-csv "$COMPARISON_CSV" \
  --disagreements-csv "$DISAGREEMENTS_CSV" \
  --summary-json "$SUMMARY_JSON"

"$PYTHON_BIN" "$ROOT_DIR/phase2/annotation/build_deberta_scope_stratified_review.py" \
  --input-csv "$COMPARISON_CSV" \
  --output-csv "$REVIEW_CSV" \
  --summary-json "$REVIEW_SUMMARY" \
  --per-stratum 5 \
  --seed 42
