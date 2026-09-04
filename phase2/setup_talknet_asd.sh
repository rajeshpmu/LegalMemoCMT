#!/usr/bin/env bash
set -euo pipefail

# Install the official TalkNet-ASD code and its runtime in an isolated venv.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TALKNET_ROOT="${TALKNET_ROOT:-$ROOT_DIR/.third_party/TalkNet-ASD}"
TALKNET_VENV="${TALKNET_VENV:-$ROOT_DIR/.venv-talknet}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$(dirname "$TALKNET_ROOT")"
if [[ ! -d "$TALKNET_ROOT/.git" ]]; then
  git clone https://github.com/TaoRuijie/TalkNet-ASD.git "$TALKNET_ROOT"
else
  echo "Using existing TalkNet checkout: $TALKNET_ROOT"
fi

if [[ ! -x "$TALKNET_VENV/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$TALKNET_VENV"
fi

PIP="$TALKNET_VENV/bin/pip"
PY="$TALKNET_VENV/bin/python"
"$PIP" install --upgrade pip

# The upstream demo uses the legacy scenedetect API and MFCC preprocessing.
"$PIP" install \
  "numpy<2" \
  "scipy" \
  "scikit-learn" \
  "pandas" \
  "opencv-python" \
  "python-speech-features" \
  "scenedetect<0.6" \
  "tqdm" \
  "gdown"

if ! "$PY" -c 'import torch' >/dev/null 2>&1; then
  echo "PyTorch is not installed; installing the current PyPI build."
  "$PIP" install torch torchvision
fi

"$PY" - <<'PY'
import torch
print(f"torch={torch.__version__}")
print(f"cuda_available={torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"gpu={torch.cuda.get_device_name(0)}")
PY

MODEL_PATH="${TALKNET_MODEL:-$TALKNET_ROOT/pretrain_TalkSet.model}"
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Downloading the official pretrained TalkSet checkpoint to: $MODEL_PATH"
  # Current gdown accepts the Drive file ID as a positional argument.
  "$TALKNET_VENV/bin/gdown" "1AbN9fCf9IexMxEKXLQY2KYBlb-IhSEea" -O "$MODEL_PATH"
fi

cat <<EOF
TalkNet setup complete.
TALKNET_ROOT=$TALKNET_ROOT
TALKNET_VENV=$TALKNET_VENV
TALKNET_MODEL=$MODEL_PATH
Use the project wrapper with:
  TALKNET_ROOT=$TALKNET_ROOT TALKNET_VENV=$TALKNET_VENV TALKNET_MODEL=$MODEL_PATH \\
  bash phase2/asd/run_tupac_talknet_asd.sh --max-rows 10 --skip-existing
EOF
