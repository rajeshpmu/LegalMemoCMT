#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/workspace/LegalMemoCMT}"
cd "$ROOT_DIR"

bash scripts/runpod_run_meld_vit_facecrop_gated_video_aux_fold2.sh "$@"
bash scripts/runpod_analyze_meld_vit_facecrop_gated_video_aux_fold2.sh
bash scripts/runpod_run_meld_vit_facecrop_gated_video_aux_fold4.sh
bash scripts/runpod_analyze_meld_vit_facecrop_gated_video_aux_fold4.sh

echo "RunPod MELD face-crop gated + video-aux suite complete."
