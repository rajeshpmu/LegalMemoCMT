#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PHASE2_MANIFEST="${PHASE2_MANIFEST:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset.csv}"
INIT_CKPT="${INIT_CKPT:-$ROOT_DIR/results/phase1/meld_full/best_model.pt}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/results/phase2/legalmemocmt_phase2}"
EVAL_JSON="${EVAL_JSON:-$OUT_DIR/metrics.json}"
DEVICE="${DEVICE:-auto}"

if [ "$DEVICE" = "auto" ] && command -v nvidia-smi >/dev/null 2>&1; then
  DEVICE="cuda"
fi

echo "Phase 2 full run"
echo "Dataset manifest: $PHASE2_MANIFEST"
echo "Init checkpoint: $INIT_CKPT"
echo "Output dir: $OUT_DIR"
echo "Device: $DEVICE"

bash "$ROOT_DIR/phase2/run_phase2_dataset_pipeline.sh"
bash "$ROOT_DIR/phase2/run_phase2_finetune.sh" "$PHASE2_MANIFEST" --device "$DEVICE" --init-checkpoint "$INIT_CKPT" --output-dir "$OUT_DIR"
bash "$ROOT_DIR/phase2/evaluate_phase2_checkpoint.sh" "$PHASE2_MANIFEST" "$OUT_DIR/best_model.pt" "$EVAL_JSON" test

echo "Phase 2 full run complete."

