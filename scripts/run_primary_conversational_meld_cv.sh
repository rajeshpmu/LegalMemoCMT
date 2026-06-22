#!/usr/bin/env bash
set -euo pipefail

# Primary conversational benchmark for the new approach.
# MELD remains the dialogue-level benchmark, but is now clearly separated
# from the primary speech-emotion CREMA-D track.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MELD_RAW_MANIFEST="${MELD_RAW_MANIFEST:-data/manifests/meld_raw.csv}"
MELD_CV_DIR="${MELD_CV_DIR:-data/manifests/meld_cv_primary}"
RESULTS_DIR="${RESULTS_DIR:-results/primary_conversational/meld_cv/cmt_min}"
LOCK_FILE="${LOCK_FILE:-/tmp/LegalMemoCMT_primary_benchmark.lock}"

mkdir -p "$(dirname "$RESULTS_DIR")"

"$PYTHON_BIN" scripts/build_meld_raw_manifest.py \
  --meld-root data/MELD \
  --manifest-dir data/manifests

if [ -f "$LOCK_FILE" ]; then
  echo "Another primary benchmark run appears to be active: $LOCK_FILE" >&2
  echo "Run the new benchmark workflows sequentially rather than in parallel." >&2
  exit 1
fi

if ps -axo command | rg -q "run_primary_conversational_meld_cv|run_primary_speech_emotion_crema_d_cv|src\\.train\\.train"; then
  echo "Another primary benchmark training process is already active." >&2
  echo "Wait for it to finish, or stop it before starting this MELD CV run." >&2
  exit 1
fi

trap 'rm -f "$LOCK_FILE"' EXIT
touch "$LOCK_FILE"

"$PYTHON_BIN" scripts/build_meld_cv_folds.py \
  --manifest "$MELD_RAW_MANIFEST" \
  --output-dir "$MELD_CV_DIR" \
  --num-folds 5 \
  --seed 42 \
  --base-splits train,dev

for fold in 0 1 2 3 4; do
  fold_dir="${RESULTS_DIR}/fold_${fold}"
  train_manifest="${MELD_CV_DIR}/meld_fold_${fold}_train.csv"
  val_manifest="${MELD_CV_DIR}/meld_fold_${fold}_val.csv"

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
    --manifest "$MELD_RAW_MANIFEST" \
    --split test \
    --checkpoint "$fold_dir/best_model.pt" \
    --output-json "$fold_dir/metrics.json" \
    --output-predictions-csv "$fold_dir/predictions_test.csv" \
    --encoder-mode paper \
    --device cpu \
    --modalities "text,audio" \
    --fusion-pooling min \
    --batch-size 4
done

"$PYTHON_BIN" scripts/aggregate_fold_metrics.py \
  --input-dir "$RESULTS_DIR" \
  --pattern "fold_*/metrics.json" \
  --output-json "$RESULTS_DIR/summary.json" \
  --output-md "$RESULTS_DIR/summary.md"

echo "Primary conversational MELD 5-fold CV complete."
