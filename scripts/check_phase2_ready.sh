#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "$ROOT_DIR/scripts/check_phase2_dataset_ready.sh" "$@"
echo
bash "$ROOT_DIR/scripts/check_phase2_finetune_ready.sh" "$@"
