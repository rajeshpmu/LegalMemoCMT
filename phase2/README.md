# Phase 2 pipeline

This directory contains the Phase 2 legal-domain adaptation workflow for LegalMemoCMT.

The current implementation is now driven by two local source CSVs stored under:

- `data/phase2/source_manifests/tribunal_sources_target_dataset.csv`
- `data/phase2/source_manifests/witness_harvest_manifest.csv`

## What Phase 2 is trying to do

Phase 2 moves the Phase 1 multimodal emotion model into courtroom and judicial-record settings. The goal is still observable emotion analysis, not legal judgment. The planned outputs are emotion scores, stress-oriented timelines, and emotional transitions inside testimony.

Important distinction:

- `tribunal_sources_target_dataset.csv` and `witness_harvest_manifest.csv` are planning manifests only.
- They do not represent the completed dataset.
- The final LegalMemoCMT dataset is produced only after:
  - case and witness resolution
  - transcript and video download
  - transcript segmentation into utterances
  - audio extraction from validated videos
  - final manifest generation

Corpus expansion path:

- start from the case candidate ledger
- build tribunal and witness manifests from the ledger
- expand planning manifests into a larger candidate inventory
- resolve each case to all available UCR documents
- split the inventory into video-bearing and transcript-only manifests
- download every eligible TAP recording for tri-modal work
- keep transcript-only rows in a separate text corpus
- build the final dataset only after segmentation and audio extraction

## Progressive Adaptation

The intended transfer path for Phase 2 is progressive:

1. Start from general conversational emotion learning on `MELD`.
2. Adapt to international criminal tribunal proceedings from `IRMCT / ICTY / ICTR` to learn authentic courtroom interaction patterns.
3. Add a smaller Indian appellate-court adaptation stage using Indian Supreme Court and High Court proceedings so the model learns Indian legal discourse and courtroom conventions.

This keeps the strongest witness-testimony source as the main multimodal signal while still moving the project toward the Indian legal setting.

## Data sources

1. IRMCT / ICTR / ICTY public judicial records as the primary courtroom testimony source
2. Indian Supreme Court and High Court proceedings as a smaller final adaptation corpus for Indian legal language and courtroom conventions
3. The eyewitness incongruence paper as a structuring reference, not as the main training dataset

## Recommended run order

1. Verify the source manifests are present in `data/phase2/source_manifests/`.
2. If you are on RunPod and want a single readiness report, run:
   - `bash scripts/check_phase2_runpod_sources.sh`
3. Build corpus manifests from the case ledger:
   - `bash phase2/run_build_tribunal_manifest_from_ledger.sh`
   - `bash phase2/run_build_witness_manifest_from_ledger.sh`
4. Inspect and download UCR recordings with fallback resolution:
   - `bash phase2/run_ucr_case_videos_with_fallback.sh`
   - this checks `ByCaseDocsByLang`, then `ByMainCase`, and can optionally allow non-`TAP` recordings
   - for Phase 2 tri-modal training, prefer the stricter video-only variant:
     - `bash phase2/run_ucr_case_videos_strict.sh`
     - this keeps only real video files and skips transcript-only fallbacks
   - for broad corpus expansion across all tapes in a case, use:
     - `bash phase2/run_ucr_case_videos_all_tapes.sh`
5. Split the UCR inventory by media type:
   - `bash phase2/run_split_ucr_inventory_by_media_type.sh`
6. Run the phase 2 dataset pipeline wrapper:
   - `bash phase2/run_phase2_dataset_pipeline.sh`
7. Check whether the Phase 2 dataset artifacts are ready:
   - `bash scripts/check_phase2_dataset_ready.sh`
   - or `bash scripts/check_phase2_ready.sh`
   - this now also prints the Phase 2 language profile for the manifest
8. Build a split-bearing training manifest:
   - `bash phase2/run_phase2_split_manifest.sh`
9. Sanitize the split manifest for training:
   - `bash phase2/run_phase2_sanitize_manifest.sh`
   - this removes HTML-only rows and keeps the transcript-only cleaning separate from audio extraction
10. Verify that the downloaded video files are real media files:
   - `bash scripts/check_phase2_video_integrity.sh`
   - this catches HTML pages or broken downloads before extraction
11. Extract audio from video into a tri-modal training manifest:
   - `bash phase2/run_phase2_extract_audio.sh`
   - this fills `audio_path` from the available video files and writes the tri-modal manifest
   - on GPU-enabled RunPod systems, set `USE_CUDA=1` to try CUDA-assisted ffmpeg decoding with CPU fallback
12. Check whether the Phase 2 fine-tuning inputs are ready:
   - `bash scripts/check_phase2_finetune_ready.sh`
   - this confirms the tri-modal manifest and the warm-start checkpoint at `results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt`
13. Fine-tune from the best MELD checkpoint:
   - `bash phase2/run_phase2_finetune.sh`
14. Evaluate the saved checkpoint:
   - `bash phase2/evaluate_phase2_checkpoint.sh <manifest.csv> <checkpoint.pt> <output.json>`
15. If you want a single chained run, use:
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
8. `phase2/run_phase2_split_manifest.sh`
9. `phase2/run_phase2_sanitize_manifest.sh`
10. `phase2/run_phase2_finetune.sh`
11. `phase2/evaluate_phase2_checkpoint.sh`

## Wrapper summary

- `phase2/run_phase2_dataset_pipeline.sh` runs the data-preparation stages.
- `phase2/run_build_tribunal_manifest_from_ledger.sh` builds the tribunal candidate manifest from the case ledger.
- `phase2/run_build_witness_manifest_from_ledger.sh` builds the witness candidate manifest from the case ledger.
- `phase2/run_build_ucr_case_inventory.sh` enumerates all UCR documents for planning-manifest cases.
- `phase2/run_expand_phase2_planning_manifests.sh` expands the planning manifests into a larger candidate inventory.
- `phase2/run_split_ucr_inventory_by_media_type.sh` splits the inventory into video-bearing and transcript-only manifests.
- `phase2/run_ucr_case_videos_with_fallback.sh` downloads UCR recordings using `ByCaseDocsByLang`, `ByMainCase`, and optional non-`TAP` fallback.
- `phase2/run_ucr_case_videos_strict.sh` downloads only real video files for tri-modal Phase 2.
- `phase2/run_ucr_case_videos_all_tapes.sh` downloads every eligible TAP recording for a case.
- `phase2/run_scotus_text_manifest.sh` builds a text-only Phase 2 manifest from downloaded Supreme Court transcripts.
- `phase2/run_phase2_split_manifest.sh` adds the train/dev/test split column needed by the trainer.
- `phase2/run_phase2_sanitize_manifest.sh` cleans transcript rows and can extract audio from video when needed.
- `phase2/run_phase2_extract_audio.sh` fills missing audio paths by extracting audio from the available video files.
- `phase2/run_phase2_finetune.sh` starts Phase 2 fine-tuning from the warm-start checkpoint.
- `phase2/evaluate_phase2_checkpoint.sh` evaluates the saved Phase 2 checkpoint.
- `phase2/run_phase2_full.sh` chains dataset prep, fine-tuning, and evaluation in one command.
- `scripts/check_phase2_sources_ready.sh` checks the source corpora directories.
- `scripts/check_phase2_runpod_sources.sh` checks source corpora, split manifest, and warm-start readiness in one command.
- `scripts/check_phase2_language_distribution.sh` reports English, Devanagari, other-script, and mixed-language shares for a Phase 2 manifest.
- `scripts/check_phase2_video_integrity.sh` verifies that the stored video files are actual media files and not HTML error pages.
- `phase2/download_ucr_video.py` downloads one direct UCR/IRMCT video URL for manual verification.
- `phase2/download_ucr_case_video.py` logs into UCR, finds a case recording via the API, downloads one MP4, and can verify it with `file` and `ffprobe`.

## UCR login support

If the UCR portal requires sign-in for a record, set credentials through environment variables only:

- `UCR_USERNAME`
- `UCR_PASSWORD`

The batch downloader, manual one-video downloader, and dataset builder will reuse that authenticated session when the variables are present. The repo does not store or print the password.

For a direct case-based download, use:

```bash
python3 phase2/download_ucr_case_video.py --case-number IT-95-5/18 --verify
```

You can narrow the choice by date or title substring if a case has more than one recording:

```bash
python3 phase2/download_ucr_case_video.py --case-number IT-95-5/18 --date 24/03/2016 --index 1 --verify
```

## Dataset builder entrypoint

The main manifest-driven implementation lives in:

- `phase2/dataset_builder.py`
- `phase2/run_phase2_dataset_pipeline.sh`
- `phase2/run_phase2_split_manifest.sh`
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

In other words, the pipeline is:

1. Start with planning manifests.
2. Resolve real transcript and video URLs from public sources.
3. Download and materialize the files.
4. Segment transcripts into utterances.
5. Extract audio from the verified videos.
6. Build the final `LegalMemoCMT` dataset CSV.

The dataset readiness check also prints a language profile for the current Phase 2 manifest:

- English share
- Devanagari share
- other-script share
- mixed-language warning when unexpected script mixing is detected

The Phase 2 finetuning path is explicitly tri-modal:

- `text`
- `audio`
- `video`

The audio branch is populated by extracting audio from the courtroom video files before warm-start training.
On RunPod, `phase2/run_phase2_extract_audio.sh` can try CUDA-assisted decoding when `USE_CUDA=1`, but it will fall back to CPU ffmpeg if the container build does not support GPU decode.

## Important scope note

IRMCT / ICTY / ICTR records are the main multimodal courtroom source in the current Phase 2 setup because they provide the most direct witness-testimony style material.

Indian Supreme Court and High Court proceedings are still useful, but in this plan they are a smaller adaptation stage for Indian legal language, phrasing, and courtroom conventions. They are typically text-heavy, so they support the Indian-domain adaptation layer more than the multimodal testimony layer.

The multimodal courtroom fine-tuning set should continue to come from records that actually contain audio or video, while the Indian court text corpus can be used for language adaptation and weak supervision design.

## Default warm-start checkpoint

The current default Phase 2 initialization checkpoint is:

- `results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt`

If you want to override it, set `INIT_CKPT` before running the Phase 2 shell wrappers.
