#!/usr/bin/env bash
set -euo pipefail

bash scripts/run_meld_vit_facecrop_gated_video_aux_fold2.sh "$@"
bash scripts/analyze_meld_vit_facecrop_gated_video_aux_fold2.sh
bash scripts/run_meld_vit_facecrop_gated_video_aux_fold4.sh
bash scripts/analyze_meld_vit_facecrop_gated_video_aux_fold4.sh

echo "MELD face-crop gated + video-aux suite complete."
