#!/usr/bin/env bash
set -euo pipefail

# Paper-aligned CREMA-D runner.
# Mirrors the pretrained text+audio setup used for MELD:
# - BERT text encoder
# - HuBERT audio encoder
# - bidirectional cross-attention CMT
# - MIN pooling as the main fusion choice
# - fine-tuned pretrained backbones
# - held-out train/val/test protocol based on the CREMA-D manifest

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
CREMA_MANIFEST="data/manifests/crema_d.csv"
OUT_DIR="results/paper_aligned_crema_d/cmt_min"

mkdir -p results/paper_aligned_crema_d

if [ ! -f "$CREMA_MANIFEST" ]; then
  echo "Missing CREMA-D manifest: $CREMA_MANIFEST"
  echo "Build it first with scripts/build_crema_d_manifest.py."
  exit 1
fi

"$PYTHON_BIN" -m src.train.train \
  --manifest "$CREMA_MANIFEST" \
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
  --manifest "$CREMA_MANIFEST" \
  --split test \
  --checkpoint "$OUT_DIR/best_model.pt" \
  --output-json "$OUT_DIR/metrics.json" \
  --output-predictions-csv "$OUT_DIR/predictions_test.csv" \
  --encoder-mode paper \
  --device cpu \
  --modalities "text,audio" \
  --fusion-pooling min \
  --batch-size 4

echo "Paper-aligned CREMA-D run complete."
