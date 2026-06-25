#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MANIFEST="${1:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv}"
INIT_CKPT="${INIT_CKPT:-$ROOT_DIR/results/phase1/meld_full/best_model.pt}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/results/phase2/legalmemocmt_phase2}"
DEVICE="${DEVICE:-auto}"

if [ "$DEVICE" = "auto" ] && command -v nvidia-smi >/dev/null 2>&1; then
  DEVICE="cuda"
fi

if [ ! -f "$INIT_CKPT" ]; then
  echo "Missing MELD checkpoint: $INIT_CKPT" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

"$PYTHON_BIN" "$ROOT_DIR/phase2/train_phase2_from_checkpoint.py" \
  --manifest "$MANIFEST" \
  --init-checkpoint "$INIT_CKPT" \
  --output-dir "$OUT_DIR" \
  --encoder-mode paper \
  --fusion-mode gated \
  --modalities text,audio \
  --loss-type weighted-ce \
  --epochs 5 \
  --batch-size 4 \
  --lr 5e-5 \
  --train-split train \
  --val-split dev \
  --device "$DEVICE" \
  "$@"
