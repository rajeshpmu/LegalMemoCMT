# Phase 2 pipeline

This directory contains the Phase 2 legal-domain adaptation workflow for LegalMemoCMT.

The current implementation is driven by the tribunal bootstrap corpus and the witness-level manifests that are produced from the verified inventory.

## What Phase 2 is trying to do

Phase 2 moves the Phase 1 multimodal emotion model into courtroom and judicial-record settings. The goal is still observable emotion analysis, not legal judgment. The planned outputs are emotion scores, stress-oriented timelines, and emotional transitions inside testimony.

The scope now has two layers:

- a tribunal bootstrap layer built from ICTY / ICTR / IRMCT testimony
- an Indian courtroom adaptation layer built from Indian legal speech, livestreams, and mock-trial style material where synchronized transcript/audio/video evidence is available

The tribunal data is the supervised proof-of-pipeline corpus. The Indian data is the actual research adaptation target.

Important distinction:

- `tribunal_sources_target_dataset.csv` and `witness_harvest_manifest.csv` are planning manifests only.
- They do not represent the completed dataset.
- The current `witness_harvest_manifest.csv` is a placeholder and must not drive downloads until it contains real witness/hearing rows and resolved links.
- The final LegalMemoCMT dataset is produced only after:
  - case and witness resolution
  - transcript and video download
  - transcript segmentation into utterances
  - audio extraction from validated videos
  - final manifest generation

Corpus expansion path:

- start from the case candidate ledger
- deduplicate the merged candidate ledgers
- crawl official UCR case pages for new case-family candidates
- enrich the ledger by checking official UCR case pages
- build tribunal and witness manifests from the ledger
- expand planning manifests into a larger candidate inventory
- resolve each case to all available UCR documents
- split the inventory into video-bearing and transcript-only manifests
- download every eligible TAP recording for tri-modal work
- keep transcript-only rows in a separate text corpus
- build the final dataset only after segmentation and audio extraction
- after the tribunal bootstrap is stable, mirror the same manifest-and-alignment logic for Indian sources

## Progressive Adaptation

The intended transfer path for Phase 2 is progressive:

1. Start from general conversational emotion learning on `MELD`.
2. Adapt to international criminal tribunal proceedings from `IRMCT / ICTY / ICTR` to learn authentic courtroom interaction patterns.
3. Add an Indian adaptation stage using Indian Supreme Court and High Court proceedings, plus mock-trial and academy material when synchronized media and transcripts exist, so the model learns Indian legal discourse and courtroom conventions.

This keeps the strongest witness-testimony source as the main multimodal signal while still moving the project toward the Indian legal setting.

Recommended interpretation:

- tribunal corpus = bootstrap supervision
- Indian corpus = target-domain adaptation and evaluation
- mock-trial and academy material = practical supplement where real Indian witness video is not public

## Data sources

1. IRMCT / ICTR / ICTY public judicial records as the primary tribunal bootstrap source
2. Indian Supreme Court and High Court proceedings as the adaptation source for Indian legal language and courtroom conventions
3. Indian mock trials and judicial-academy material where synchronized video and transcript material is available
4. The eyewitness incongruence paper as a structuring reference, not as the main training dataset

## Recommended run order

1. Verify the source manifests are present in `data/phase2/source_manifests/`.
2. If you are on RunPod and want a single readiness report, run:
   - `bash scripts/check_phase2_runpod_sources.sh`
3. Deduplicate the merged candidate ledger:
   - `bash phase2/run_deduplicate_case_ledger.sh`
4. Crawl official UCR case pages for new candidate families:
   - `bash phase2/run_crawl_official_ucr_case_pages.sh`
5. Enrich the ledger from the official UCR case pages:
   - `bash phase2/run_enrich_case_ledger_from_ucr_site.sh`
6. Build corpus manifests from the case ledger:
   - `bash phase2/run_build_tribunal_manifest_from_ledger.sh`
   - `bash phase2/run_build_witness_manifest_from_ledger.sh`
7. Build the verified UCR case inventory from the enriched ledger:
   - `bash phase2/run_build_ucr_case_inventory.sh`
8. Inspect and download UCR recordings with fallback resolution:
   - `bash phase2/run_ucr_case_videos_with_fallback.sh`
   - this checks `ByCaseDocsByLang`, then `ByMainCase`, and can optionally allow non-`TAP` recordings
   - for Phase 2 tri-modal training, prefer the stricter video-only variant:
     - `bash phase2/run_ucr_case_videos_strict.sh`
     - this keeps only real video files and skips transcript-only fallbacks
   - for broad corpus expansion across all tapes in a case, use:
     - `bash phase2/run_ucr_case_videos_all_tapes.sh`
9. Split the UCR inventory by media type:
   - `bash phase2/run_split_ucr_inventory_by_media_type.sh`
10. Run the phase 2 dataset pipeline wrapper:
   - `bash phase2/run_phase2_dataset_pipeline.sh`
11. Check whether the Phase 2 dataset artifacts are ready:
   - `bash scripts/check_phase2_dataset_ready.sh`
   - or `bash scripts/check_phase2_ready.sh`
   - this now also prints the Phase 2 language profile for the manifest
12. Build a split-bearing training manifest:
   - `bash phase2/run_phase2_split_manifest.sh`
13. Sanitize the split manifest for training:
   - `bash phase2/run_phase2_sanitize_manifest.sh`
   - this removes HTML-only rows and keeps the transcript-only cleaning separate from audio extraction
14. Verify that the downloaded video files are real media files:
   - `bash scripts/check_phase2_video_integrity.sh`
   - this catches HTML pages or broken downloads before extraction
15. Extract audio from video into a tri-modal training manifest:
   - `bash phase2/run_phase2_extract_audio.sh`
   - this fills `audio_path` from the available video files and writes the tri-modal manifest
   - on GPU-enabled RunPod systems, set `USE_CUDA=1` to try CUDA-assisted ffmpeg decoding with CPU fallback
16. Build the LegalMELD utterance-level dataset:
   - `bash phase2/run_build_legalmeld_dataset.sh`
   - this parses transcript speaker turns, aligns them to word timestamps, and writes `legalmeld_metadata.csv` plus `train.csv`, `dev.csv`, and `test.csv`
   - the output layout mirrors MELD with per-utterance `clips/`, `audio/`, `transcripts/`, and `labels/` folders
17. If you want to focus only on testimony rows, build the witness-only planning subset:
   - `bash phase2/run_filter_legalmeld_rows_by_witness_role.sh`
   - this keeps only `speaker_role = Witness` rows from the validated utterance export and preserves the usable/review/reject buckets
   - the outputs land in `data/processed/phase2/legalmeld_validated/witness_only_rows/`
18. Promote a small controlled validation subset from the broader hearing plan:
   - `bash phase2/run_build_witness_controlled_validation_subset.sh`
   - this keeps the validated witness hearings as anchors and adds a small number of manually promoted hearings for tighter inspection
   - the outputs land in `data/processed/phase2/legalmeld_validated/witness_only_rows/witness_controlled_validation_subset.csv`
19. If you are extending the dissertation toward the Indian scope, prepare the Indian acquisition pack and adaptation manifests next:
   - `indian_case_candidate_ledger.csv`
   - `indian_video_sources.csv`
   - `indian_mock_trial_manifest.csv`
   - `indian_supreme_court_manifest.csv`
   - `indian_high_court_manifest.csv`
   - `indian_alignment_manifest.csv`
20. Check whether the Phase 2 fine-tuning inputs are ready:
   - `bash scripts/check_phase2_finetune_ready.sh`
   - this confirms the tri-modal manifest and the warm-start checkpoint at `results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt`
21. Fine-tune from the best MELD checkpoint:
   - `bash phase2/run_phase2_finetune.sh`
22. Evaluate the saved checkpoint:
   - `bash phase2/evaluate_phase2_checkpoint.sh <manifest.csv> <checkpoint.pt> <output.json>`
23. If you want a single chained run, use:
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
- `phase2/run_deduplicate_case_ledger.sh` merges and deduplicates the candidate ledgers.
- `phase2/run_crawl_official_ucr_case_pages.sh` crawls official UCR case pages for new candidate case families.
- `phase2/run_build_tribunal_manifest_from_ledger.sh` builds the tribunal candidate manifest from the case ledger.
- `phase2/run_build_witness_manifest_from_ledger.sh` builds the witness candidate manifest from the case ledger.
- `phase2/run_enrich_case_ledger_from_ucr_site.sh` checks the official UCR case pages and annotates the ledger with page-level evidence.
- `phase2/enrich_case_ledger_from_ucr_site.py` now validates control cases and writes `reports/phase2/ucr_enrichment_validation.json`.
- `phase2/run_build_ucr_case_inventory.sh` builds `verified_case_inventory.csv` from the corrected enriched ledger.
- `phase2/run_expand_phase2_planning_manifests.sh` expands the planning manifests into a larger candidate inventory.
- `phase2/run_split_ucr_inventory_by_media_type.sh` splits `verified_case_inventory.csv` into video-bearing and transcript-only manifests.
- `phase2/run_ucr_case_videos_with_fallback.sh` downloads UCR recordings using `ByCaseDocsByLang`, `ByMainCase`, and optional non-`TAP` fallback.
- `phase2/run_ucr_case_videos_strict.sh` downloads only real video files for tri-modal Phase 2.
- `phase2/run_ucr_case_videos_all_tapes.sh` downloads every eligible TAP recording for a case.
- `phase2/run_scotus_text_manifest.sh` builds a text-only Phase 2 manifest from downloaded Supreme Court transcripts.
- `phase2/run_phase2_split_manifest.sh` adds the train/dev/test split column needed by the trainer.
- `phase2/run_phase2_sanitize_manifest.sh` cleans transcript rows and can extract audio from video when needed.
- `phase2/run_phase2_extract_audio.sh` fills missing audio paths by extracting audio from the available video files.
- `phase2/run_build_legalmeld_dataset.sh` builds the utterance-level LegalMELD dataset with aligned clips and MELD-style split CSVs.
- `phase2/run_filter_legalmeld_rows_by_witness_role.sh` filters the validated utterance export down to witness-only planning rows and writes usable/review/reject witness buckets.
- `phase2/run_build_witness_controlled_validation_subset.sh` promotes a small controlled validation subset from the broader hearing discovery plan.
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

Indian Supreme Court and High Court proceedings are still useful, but in this plan they are the adaptation stage for Indian legal language, phrasing, and courtroom conventions. They are often argument-heavy rather than witness-heavy, so they support the Indian-domain adaptation layer more than the multimodal testimony layer.

The multimodal courtroom fine-tuning set should continue to come from records that actually contain audio or video, while the Indian court corpus can be used for language adaptation, weak supervision design, and evaluation of transfer beyond the tribunal bootstrap set.

If you need the dissertation narrative in one line:

- Phase 2 proves the utterance-level pipeline on tribunal testimony.
- Phase 2 then reuses that pipeline to adapt LegalMemoCMT toward Indian courtroom testimony.

## Default warm-start checkpoint

The current default Phase 2 initialization checkpoint is:

- `results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt`

If you want to override it, set `INIT_CKPT` before running the Phase 2 shell wrappers.
