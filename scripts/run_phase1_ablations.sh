#!/usr/bin/env bash
set -euo pipefail

# Optional experiment suite for the adapted LegalMemoCMT objective.
# Runs modality ablations and an imbalance-aware variant on the full manifests.

mkdir -p results/phase1_ablation

run_one() {
  local tag="$1"
  local manifest="$2"
  local modalities="$3"
  local loss_type="$4"
  local gamma="${5:-2.0}"
  local out_dir="results/phase1_ablation/${tag}"

  python3 -m src.train.train \
    --manifest "$manifest" \
    --output-dir "$out_dir" \
    --modalities "$modalities" \
    --loss-type "$loss_type" \
    --focal-gamma "$gamma"
  python3 -m src.train.evaluate \
    --manifest "$manifest" \
    --checkpoint "$out_dir/best_model.pt" \
    --output-json "$out_dir/metrics.json" \
    --modalities "$modalities"
}

# Unimodal ablations
run_one "meld_text_only" "data/manifests/meld_train.csv" "text" "weighted-ce"
run_one "meld_audio_only" "data/manifests/meld_train.csv" "audio" "weighted-ce"
run_one "meld_video_only" "data/manifests/meld_train.csv" "video" "weighted-ce"
run_one "meld_multimodal_weighted" "data/manifests/meld_train.csv" "text,audio,video" "weighted-ce"
run_one "meld_multimodal_focal" "data/manifests/meld_train.csv" "text,audio,video" "focal" "2.0"

run_one "crema_text_only" "data/manifests/crema_d.csv" "text" "weighted-ce"
run_one "crema_audio_only" "data/manifests/crema_d.csv" "audio" "weighted-ce"
run_one "crema_video_only" "data/manifests/crema_d.csv" "video" "weighted-ce"
run_one "crema_multimodal_weighted" "data/manifests/crema_d.csv" "text,audio,video" "weighted-ce"
run_one "crema_multimodal_focal" "data/manifests/crema_d.csv" "text,audio,video" "focal" "2.0"

echo "Ablation suite complete."
