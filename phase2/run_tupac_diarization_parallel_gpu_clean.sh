#!/usr/bin/env bash
set -euo pipefail

# RunPod-only launcher: prevent host/Conda CUDA paths from overriding the
# cuDNN libraries bundled with the PyTorch wheel.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv-diarization/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

unset LD_LIBRARY_PATH
export PYTHONNOUSERSITE=1

"$PYTHON_BIN" - <<'PY'
import torch

if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable")
print(f"torch={torch.__version__} cuda={torch.version.cuda}")
print(f"gpu={torch.cuda.get_device_name(0)}")
print("cuda_probe=", torch.randn(2, 2, device="cuda") @ torch.randn(2, 2, device="cuda"))
PY

exec env -u LD_LIBRARY_PATH \
  PYTHON_BIN="$PYTHON_BIN" \
  bash "$ROOT_DIR/phase2/run_clancy_diarization_parallel.sh" "$@"
