#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv-diarization/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

# Avoid stale Conda/container CUDA paths overriding the wheel's bundled cuDNN.
unset LD_LIBRARY_PATH
export PYTHONNOUSERSITE=1
"$PYTHON_BIN" - <<'PY'
import torch
assert torch.cuda.is_available(), "CUDA is unavailable"
print(f"torch={torch.__version__} cuda={torch.version.cuda}")
print(f"gpu={torch.cuda.get_device_name(0)}")
x = torch.randn(2, 2, device="cuda")
print("cuda_probe=", x @ x)
PY

exec env -u LD_LIBRARY_PATH PYTHON_BIN="$PYTHON_BIN" \
  "$PYTHON_BIN" "$ROOT_DIR/phase2/run_tupac_diarization_parallel_pyannote4.py" "$@"
