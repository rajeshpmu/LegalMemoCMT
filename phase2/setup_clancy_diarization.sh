#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BOOTSTRAP_PYTHON="${BOOTSTRAP_PYTHON:-/usr/bin/python3}"
DIARIZATION_VENV="${DIARIZATION_VENV:-$ROOT_DIR/.venv-diarization}"
PYTHON_BIN="${PYTHON_BIN:-$DIARIZATION_VENV/bin/python}"
PYANNOTE_SPEC="${PYANNOTE_SPEC:-pyannote.audio==3.4.0}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Creating isolated diarization environment: $DIARIZATION_VENV"
  "$BOOTSTRAP_PYTHON" -m venv "$DIARIZATION_VENV"
  PYTHON_BIN="$DIARIZATION_VENV/bin/python"
fi

echo "Installing pyannote.audio into: $PYTHON_BIN"
"$PYTHON_BIN" -m pip install --upgrade pip
# pyannote.audio 3.4 calls hf_hub_download with the legacy use_auth_token
# keyword. Hub 0.13.4 still translates that call compatibly; Hub 1.x does not.
"$PYTHON_BIN" -m pip install "numpy<2.0" "torch==2.2.2" "torchaudio==2.2.2" "huggingface_hub==0.13.4" "$PYANNOTE_SPEC"

if [[ -z "${HF_TOKEN:-}" && -z "${HUGGINGFACE_TOKEN:-}" ]]; then
  echo "Installation completed. Set HF_TOKEN before model-access verification." >&2
  exit 0
fi

"$PYTHON_BIN" phase2/check_clancy_diarization_prerequisites.py \
  --model "${DIARIZATION_MODEL:-pyannote/speaker-diarization-3.1}" \
  --load-model
