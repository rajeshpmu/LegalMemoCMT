#!/usr/bin/env bash
set -euo pipefail

# Paper-style CREMA-D cross-validation workflow.
# This is the stricter speech-emotion track: speaker-independent folds and
# summary reporting in terms of W-Acc / UW-Acc.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
CREMA_MANIFEST="${CREMA_MANIFEST:-data/manifests/crema_d.csv}"
CV_DIR="${CV_DIR:-data/manifests/crema_d_cv}"
RESULTS_DIR="${RESULTS_DIR:-results/primary_speech_emotion/crema_d_cv/cmt_min}"
LOCK_FILE="${LOCK_FILE:-/tmp/LegalMemoCMT_primary_benchmark.lock}"

mkdir -p "$(dirname "$RESULTS_DIR")"

if [ ! -f "$CREMA_MANIFEST" ]; then
  echo "Missing CREMA-D manifest: $CREMA_MANIFEST" >&2
  echo "Build it first with scripts/build_crema_d_manifest.py." >&2
  exit 1
fi

if [ -f "$LOCK_FILE" ]; then
  echo "Another primary benchmark run appears to be active: $LOCK_FILE" >&2
  echo "Run the new benchmark workflows sequentially rather than in parallel." >&2
  exit 1
fi

if ps -axo command | rg -q "run_primary_conversational_meld_cv|run_primary_speech_emotion_crema_d_cv|src\\.train\\.train"; then
  echo "Another primary benchmark training process is already active." >&2
  echo "Wait for it to finish, or stop it before starting this CREMA-D CV run." >&2
  exit 1
fi

trap 'rm -f "$LOCK_FILE"' EXIT
touch "$LOCK_FILE"

"$PYTHON_BIN" scripts/build_crema_d_cv_folds.py \
  --manifest "$CREMA_MANIFEST" \
  --output-dir "$CV_DIR" \
  --num-folds 5 \
  --seed 42

for fold in 0 1 2 3 4; do
  fold_dir="${RESULTS_DIR}/fold_${fold}"
  train_manifest="${CV_DIR}/crema_d_fold_${fold}_train.csv"
  val_manifest="${CV_DIR}/crema_d_fold_${fold}_val.csv"

  "$PYTHON_BIN" -m src.train.train \
    --manifest "$train_manifest" \
    --val-manifest "$val_manifest" \
    --output-dir "$fold_dir" \
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
    --manifest "$val_manifest" \
    --split val \
    --checkpoint "$fold_dir/best_model.pt" \
    --output-json "$fold_dir/metrics.json" \
    --output-predictions-csv "$fold_dir/predictions_val.csv" \
    --encoder-mode paper \
    --device cpu \
    --modalities "text,audio" \
    --fusion-pooling min \
    --batch-size 4
done

"$PYTHON_BIN" scripts/aggregate_crema_d_cv_metrics.py \
  --input-dir "$RESULTS_DIR" \
  --pattern "fold_*/metrics.json" \
  --output-json "$RESULTS_DIR/summary.json" \
  --output-md "$RESULTS_DIR/summary.md"

echo "Paper-style CREMA-D CV complete."
