# Phase 2 pipeline

This directory contains the Phase 2 legal-domain adaptation workflow for LegalMemoCMT.

The current implementation is now driven by two local source CSVs stored under:

- `data/phase2/source_manifests/tribunal_sources_target_dataset.csv`
- `data/phase2/source_manifests/witness_harvest_manifest.csv`

## What Phase 2 is trying to do

Phase 2 moves the Phase 1 multimodal emotion model into courtroom and judicial-record settings. The goal is still observable emotion analysis, not legal judgment. The planned outputs are emotion scores, stress-oriented timelines, and emotional transitions inside testimony.

## Data sources

1. Supreme Court oral argument transcripts
2. IRMCT / ICTR / ICTY public judicial records
3. The eyewitness incongruence paper as a structuring reference, not as the main training dataset

## Recommended run order

1. Verify the source manifests are present in `data/phase2/source_manifests/`.
2. Run the phase 2 dataset pipeline wrapper:
   - `bash phase2/run_phase2_dataset_pipeline.sh`
3. Check whether the manifest is complete and whether raw MELD data is still needed:
   - `bash scripts/check_phase1_meld_ready.sh`
   - or `bash scripts/check_meld_ready.sh <manifest.csv>`
4. Fine-tune from the best MELD checkpoint:
   - `bash phase2/run_phase2_finetune.sh`
5. Evaluate the saved checkpoint:
   - `bash phase2/evaluate_phase2_checkpoint.sh <manifest.csv> <checkpoint.pt> <output.json>`
6. If you want a single chained run, use:
   - `bash phase2/run_phase2_full.sh`

## Device policy

- Data preparation and manifest-building steps are CPU-bound.
- Training and evaluation wrappers now prefer `cuda` automatically when `nvidia-smi` is available.
- If needed, you can still override the device with `DEVICE=cpu`, `DEVICE=mps`, or `DEVICE=cuda` before running the shell wrapper.

## Individual scripts in execution order

1. `phase2/dataset_builder.py validate-tri`
2. `phase2/dataset_builder.py validate-witness`
3. `phase2/dataset_builder.py resolve`
4. `phase2/dataset_builder.py materialize`
5. `phase2/dataset_builder.py build-dataset`
6. `phase2/dataset_builder.py weak-labels`
7. `phase2/dataset_builder.py dashboard`
8. `phase2/run_phase2_finetune.sh`
9. `phase2/evaluate_phase2_checkpoint.sh`

## Wrapper summary

- `phase2/run_phase2_dataset_pipeline.sh` runs the data-preparation stages.
- `phase2/run_phase2_finetune.sh` starts Phase 2 fine-tuning from the MELD checkpoint.
- `phase2/evaluate_phase2_checkpoint.sh` evaluates the saved Phase 2 checkpoint.
- `phase2/run_phase2_full.sh` chains dataset prep, fine-tuning, and evaluation in one command.

## Dataset builder entrypoint

The main manifest-driven implementation lives in:

- `phase2/dataset_builder.py`
- `phase2/run_phase2_dataset_pipeline.sh`
- `phase2/run_phase2_prepare.sh`

It provides the requested staged functions:

- `load_manifest()`
- `load_tribunal_sources()`
- `resolve_transcript_links()`
- `resolve_video_links()`
- `download_transcript()`
- `extract_transcript_text()`
- `download_video()`
- `extract_audio()`
- `segment_transcript()`

It also writes the requested intermediate and final artifacts:

- `data/resolved_manifest.csv`
- `data/resolved_manifest_materialized.csv`
- `data/raw/transcripts/`
- `data/raw/videos/`
- `data/raw/audio/`
- `data/processed/phase2/legalmemocmt_phase2_dataset.csv`
- `data/processed/phase2/weak_labels/`
- `reports/dataset_status.html`

## Important scope note

Supreme Court transcripts are useful for text adaptation and legal language structure. They are typically text-only, so they are not the main multimodal training set unless audio/video is also available.

The multimodal courtroom fine-tuning set should come from records that actually contain audio or video, while the text-only corpus can still be used for language adaptation and weak supervision design.
