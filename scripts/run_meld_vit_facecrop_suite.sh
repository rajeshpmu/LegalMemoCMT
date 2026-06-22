#!/usr/bin/env bash
set -euo pipefail

bash scripts/run_meld_vit_facecrop_prepare.sh "$@"
bash scripts/run_meld_vit_facecrop_fold2.sh
bash scripts/analyze_meld_vit_facecrop_fold2.sh
bash scripts/run_meld_vit_facecrop_fold4.sh
bash scripts/analyze_meld_vit_facecrop_fold4.sh

echo "MELD ViT face-crop suite complete."
