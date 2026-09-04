#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TALKNET_ROOT="${TALKNET_ROOT:-$ROOT_DIR/.third_party/TalkNet-ASD}"
TALKNET_VENV="${TALKNET_VENV:-$ROOT_DIR/.venv-talknet}"
TALKNET_MODEL="${TALKNET_MODEL:-$TALKNET_ROOT/pretrain_TalkSet.model}"
PYTHON_BIN="${PYTHON_BIN:-$TALKNET_VENV/bin/python}"
INPUT_CSV="${INPUT_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_witness_speaking_visual_review.csv}"
OUTPUT_CSV="${OUTPUT_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_witness_speaking_talknet_asd.csv}"
TRACKS_CSV="${TRACKS_CSV:-$ROOT_DIR/data/processed/phase2/tupac/tupac_talknet_face_tracks.csv}"
SUMMARY_JSON="${SUMMARY_JSON:-$ROOT_DIR/reports/phase2/tupac_talknet_asd.json}"
WORK_ROOT="${WORK_ROOT:-$ROOT_DIR/data/processed/phase2/tupac/talknet_work}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing TalkNet Python: $PYTHON_BIN" >&2
  echo "Run: bash phase2/asd/setup_talknet_asd.sh" >&2
  exit 2
fi

if [[ ! -f "$TALKNET_MODEL" ]]; then
  echo "Missing TalkNet weights: $TALKNET_MODEL" >&2
  echo "Run: bash phase2/asd/setup_talknet_asd.sh" >&2
  exit 2
fi

export PATH="$TALKNET_VENV/bin:$PATH"
"$PYTHON_BIN" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit(
        "TalkNet-ASD requires CUDA in the upstream implementation; "
        "run this wrapper on the CUDA-enabled RunPod environment."
    )
print(f"TalkNet CUDA device: {torch.cuda.get_device_name(0)}")
PY

exec "$PYTHON_BIN" "$ROOT_DIR/phase2/asd/run_talknet_asd.py" \
  --input-csv "$INPUT_CSV" \
  --output-csv "$OUTPUT_CSV" \
  --tracks-csv "$TRACKS_CSV" \
  --summary-json "$SUMMARY_JSON" \
  --talknet-root "$TALKNET_ROOT" \
  --talknet-python "$PYTHON_BIN" \
  --model "$TALKNET_MODEL" \
  --work-root "$WORK_ROOT" \
  "$@"
