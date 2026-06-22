#!/usr/bin/env bash
set -euo pipefail

# Improvement step 1:
# Re-run the CREMA-D speaker-independent CV workflow with class-balanced focal loss.

export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=1

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
CREMA_MANIFEST="${CREMA_MANIFEST:-data/manifests/crema_d.csv}"
CV_DIR="${CV_DIR:-data/manifests/crema_d_cv}"
RESULTS_DIR="${RESULTS_DIR:-results/improvement/class_balanced_focal/crema_d_cv/cmt_min}"
LOCK_FILE="${LOCK_FILE:-/tmp/LegalMemoCMT_class_balanced_focal.lock}"

mkdir -p "$(dirname "$RESULTS_DIR")"

if [ ! -f "$CREMA_MANIFEST" ]; then
  echo "Missing CREMA-D manifest: $CREMA_MANIFEST" >&2
  echo "If you need to rebuild it for a new split, uncomment the build line below." >&2
  exit 1
fi

if [ -f "$LOCK_FILE" ]; then
  echo "Another improvement run appears to be active: $LOCK_FILE" >&2
  echo "Run the improvement scripts sequentially rather than in parallel." >&2
  exit 1
fi

trap 'rm -f "$LOCK_FILE"' EXIT
touch "$LOCK_FILE"

if [ ! -f "$CV_DIR/crema_d_fold_0_train.csv" ] || [ ! -f "$CV_DIR/crema_d_fold_4_val.csv" ]; then
  echo "Missing CREMA-D fold CSVs in $CV_DIR" >&2
  echo "If you need a new split directory, uncomment the build command below." >&2
  exit 1
fi

# Rebuild only if you intentionally want a new split directory.
# "$PYTHON_BIN" scripts/build_crema_d_manifest.py \
#   --crema-root data/CREMA_D_repo \
#   --manifest-dir data/manifests \
#   --labels-csv data/CREMA_D/labels.csv
#
# "$PYTHON_BIN" scripts/build_crema_d_cv_folds.py \
#   --manifest "$CREMA_MANIFEST" \
#   --output-dir "$CV_DIR" \
#   --num-folds 5 \
#   --seed 42

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
    --loss-type focal \
    --focal-gamma 2.0 \
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

echo "Improvement CREMA-D focal-loss CV complete."
