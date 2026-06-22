#!/usr/bin/env bash
set -euo pipefail

# Primary speech-emotion benchmark for the new approach.
# CREMA-D is treated as the main speech-emotion dataset here.
# This keeps the existing paper-aligned scripts untouched.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MANIFEST="${MANIFEST:-data/manifests/crema_d.csv}"
OUT_DIR="${OUT_DIR:-results/primary_speech_emotion/crema_d/cmt_min}"

mkdir -p "$(dirname "$OUT_DIR")"

if [ ! -f "$MANIFEST" ]; then
  echo "Missing CREMA-D manifest: $MANIFEST" >&2
  echo "Build it first with scripts/build_crema_d_manifest.py." >&2
  exit 1
fi

"$PYTHON_BIN" -m src.train.train \
  --manifest "$MANIFEST" \
  --train-split train \
  --val-split val \
  --output-dir "$OUT_DIR" \
  --encoder-mode paper \
  --fine-tune-backbones \
  --device cpu \
  --modalities "text,audio" \
  --loss-type weighted-ce \
  --fusion-pooling min \
  --epochs 5 \
  --batch-size 4 \
  --lr 1e-4

"$PYTHON_BIN" -m src.train.evaluate \
  --manifest "$MANIFEST" \
  --split test \
  --checkpoint "$OUT_DIR/best_model.pt" \
  --output-json "$OUT_DIR/metrics.json" \
  --output-predictions-csv "$OUT_DIR/predictions_test.csv" \
  --encoder-mode paper \
  --device cpu \
  --modalities "text,audio" \
  --fusion-pooling min \
  --batch-size 4

echo "Primary speech-emotion CREMA-D run complete."
