#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/workspace/LegalMemoCMT}"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [ -z "${HF_TOKEN:-}" ]; then
  for token_file in "${HOME}/.huggingface/token" "${HOME}/.cache/huggingface/token"; do
    if [ -f "$token_file" ]; then
      export HF_TOKEN="$(tr -d '\n\r' < "$token_file")"
      break
    fi
  done
fi

OUTPUT_DIR="${OUTPUT_DIR:-results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4}"
PRED_CSV="${PRED_CSV:-$OUTPUT_DIR/predictions_test.csv}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$OUTPUT_DIR/analysis_test}"
RAW_MANIFEST="${RAW_MANIFEST:-data/manifests/meld_vit_facecrop.csv}"

mkdir -p "$ANALYSIS_DIR"

"$PYTHON_BIN" -m src.tools.export_predictions \
  --manifest "$RAW_MANIFEST" \
  --split test \
  --checkpoint "$OUTPUT_DIR/best_model.pt" \
  --output-csv "$PRED_CSV" \
  --batch-size "${FACECROP_ANALYZE_BATCH_SIZE:-4}" \
  --modalities "text,audio,video" \
  --fusion-pooling "${FACECROP_POOLING:-min}" \
  --fusion-mode gated \
  --encoder-mode "${FACECROP_ENCODER_MODE:-paper}" \
  --device "${FACECROP_DEVICE:-cuda}"

"$PYTHON_BIN" scripts/analyze_predictions.py \
  --predictions-csv "$PRED_CSV" \
  --output-dir "$ANALYSIS_DIR" \
  --dataset meld \
  --split test
