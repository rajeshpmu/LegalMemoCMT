#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper for the new benchmark split.
# CREMA-D is the primary speech-emotion benchmark.
# MELD is the primary conversational benchmark.

bash scripts/run_primary_speech_emotion_crema_d.sh
bash scripts/run_primary_conversational_meld_cv.sh

echo "Primary benchmark suite complete."
