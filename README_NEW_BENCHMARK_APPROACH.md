# New Benchmark Approach

This repository now supports a second, separate experiment framing in addition to the existing paper-aligned workflow.

## Track 1: Primary Speech-Emotion Benchmark

- Dataset: `CREMA-D`
- Goal: treat CREMA-D as the main speech-emotion benchmark
- Script:
  - `scripts/run_primary_speech_emotion_crema_d.sh`
- Analysis:
  - `scripts/run_primary_speech_emotion_crema_d_analysis.sh`

This track uses the same pretrained text+audio paper-aligned architecture, but it is organized around the cleaner speech-emotion dataset.

## Track 2: Primary Conversational Benchmark

- Dataset: `MELD`
- Goal: keep MELD as the paper-aligned conversational benchmark
- Script:
  - `scripts/run_primary_conversational_meld_cv.sh`
- Analysis:
  - `scripts/run_primary_conversational_meld_analysis.sh`

This track keeps the 5-fold MELD workflow and the MIN pooling result, but it is now clearly separated from the speech-emotion benchmark.

## Combined Runner

- `scripts/run_primary_benchmark_suite.sh`

Runs both tracks in sequence.

## Notes

- The existing `scripts/run_paper_aligned_*` scripts are unchanged.
- The new scripts write to separate `results/primary_*` directories so the old outputs remain intact.
- All scripts are shell wrappers only; they do not change the underlying implementation.
