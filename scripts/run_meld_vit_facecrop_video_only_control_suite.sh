#!/usr/bin/env bash
set -euo pipefail

# Dedicated control-suite for checking whether the cropped ViT face embeddings
# carry usable standalone signal before tri-modal fusion is interpreted.

bash scripts/run_meld_vit_facecrop_video_only_control_fold2.sh "$@"
bash scripts/analyze_meld_vit_facecrop_video_only_control_fold2.sh
bash scripts/run_meld_vit_facecrop_video_only_control_fold4.sh
bash scripts/analyze_meld_vit_facecrop_video_only_control_fold4.sh

echo "MELD face-crop video-only control suite complete."
