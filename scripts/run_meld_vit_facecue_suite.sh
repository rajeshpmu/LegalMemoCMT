#!/usr/bin/env bash
set -euo pipefail

bash scripts/run_meld_vit_facecue_prepare.sh "$@"
bash scripts/run_meld_vit_facecue_fold2.sh
bash scripts/analyze_meld_vit_facecue_fold2.sh
bash scripts/run_meld_vit_facecue_fold4.sh
bash scripts/analyze_meld_vit_facecue_fold4.sh

echo "MELD ViT facial-cue suite complete."
