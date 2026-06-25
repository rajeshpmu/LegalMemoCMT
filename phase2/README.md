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

1. Download the Supreme Court transcript corpus.
2. Prepare a tribunal source CSV from public archives or exported archive search results.
3. Download the tribunal records.
4. Build weak supervision labels.
5. Build the labeled Phase 2 manifest.
6. Fine-tune from the best MELD checkpoint.
7. Evaluate and inspect the predictions.

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
