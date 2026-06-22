# LegalMemoCMT Phase 1

Phase 1 reproduces a MemoCMT-style multimodal emotion recognition pipeline on benchmark datasets such as MELD. IEMOCAP is not planned for now; the recommended public replacement second benchmark is CREMA-D.

## Scope

- Input modalities: face/video, audio, transcript
- Output: emotion class prediction
- Goal: reproduce benchmark results and validate cross-modal transformer fusion

## Current implementation state

The repository now contains a working scaffold organized as:

- `data/` for raw and processed datasets
- `src/models/` for encoders and fusion modules
- `src/data/` for preprocessing and loaders
- `src/train/` for training and evaluation scripts
- `configs/` for model and dataset settings
- `notebooks/` for analysis and visualization
- `results/` for metrics, figures, and checkpoints

## Expected manifest format

Use a CSV manifest with at least these columns:

- `sample_id`
- `split`
- `label`
- `video_path`
- `audio_path`
- `transcript`

Optional columns:

- `text_tokens`
- `audio_features`
- `video_features`

The code supports both cached-feature manifests and raw-media manifests. The paper-aligned MELD workflow uses raw clips and generates fold manifests for cross-validation.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-phase1.txt
```

## Required Tools and Models

Before running any scripts, make sure the following are available:

### Python packages

- `torch`
- `transformers`
- `timm`
- `torchvision`
- `pillow`
- `opencv-python`
- `librosa`
- `scikit-learn`
- `pandas`
- `numpy`
- `tqdm`

The facial-cue / ViT path uses `transformers` and `timm`, and `torchvision` plus `pillow` are needed for image loading and preprocessing.

### Pretrained models

The scripts will download these backbones automatically on first use if they are not cached:

- `bert-base-uncased`
- `facebook/hubert-base-ls960`
- `google/vit-base-patch16-224-in21k`

### External tools / data

- MELD raw clips and annotations
- CREMA-D data if you run the speech-emotion benchmark
- A working video decoding backend through OpenCV
- Enough local disk space for extracted features, checkpoints, and results

## Dataset Pipeline

### MELD

```bash
python3 scripts/download_meld.py --output data/MELD --annotations --raw --extract
python3 scripts/build_meld_manifest.py --meld-root data/MELD --output-root data/processed/MELD --manifest-dir data/manifests
python3 scripts/build_meld_raw_manifest.py --meld-root data/MELD --manifest-dir data/manifests
python3 scripts/build_meld_cv_folds.py --manifest data/manifests/meld_raw.csv --output-dir data/manifests/meld_cv --num-folds 5 --seed 42 --base-splits train,dev
```

### IEMOCAP

IEMOCAP is deferred for now. It is not part of the immediate implementation plan.

### Optional replacement

If you want a public replacement benchmark, use **CREMA-D** instead of IEMOCAP.

```bash
python3 scripts/download_crema_d.py --output data/CREMA_D
# After cloning the CREMA-D repo with git lfs:
python3 scripts/build_crema_d_labels.py --crema-repo data/CREMA_D_repo --output-csv data/CREMA_D/labels.csv
# Then build the manifest:
python3 scripts/build_crema_d_manifest.py --crema-root data/CREMA_D --manifest-dir data/manifests --labels-csv data/CREMA_D/labels.csv
```


## Pipeline Operations SOP

Use this document for the full step-by-step workflow:

- [LegalMemoCMT_Pipeline_Operations_SOP.docx](implementation_docments/LegalMemoCMT_Pipeline_Operations_SOP.docx)

## Smoke test

```bash
python -m src.train.train --help
python -m src.train.evaluate --help
```

## Small-Run Training

Create a smaller manifest subset first, then train on it:

```bash
python3 scripts/create_subset_manifest.py --manifest data/manifests/meld_train.csv --output data/manifests/meld_train_small.csv --per-split 100
python3 scripts/create_subset_manifest.py --manifest data/manifests/crema_d.csv --output data/manifests/crema_d_small.csv --per-split 100
python3 -m src.train.train --manifest data/manifests/meld_train_small.csv --output-dir results/phase1_small/meld
python3 -m src.train.train --manifest data/manifests/crema_d_small.csv --output-dir results/phase1_small/crema_d
```

To train and evaluate in one shot:

```bash
python3 scripts/run_small_train_and_eval.sh
```

To save metrics as JSON:

```bash
bash scripts/evaluate_checkpoint_to_json.sh data/manifests/crema_d_small.csv results/phase1_small/crema_d/best_model.pt results/phase1_small/crema_d/metrics.json
```

To export predicted vs actual labels for error analysis:

```bash
python3 scripts/export_predictions.py --manifest data/manifests/crema_d.csv --split test --checkpoint results/phase1/crema_d_full/best_model.pt --output-csv results/phase1/crema_d_full/predictions.csv
```

Preferred held-out wrapper:

```bash
bash scripts/export_predictions_from_eval.sh data/manifests/crema_d.csv results/phase1/crema_d_full/best_model.pt results/phase1/crema_d_full/predictions_test.csv test
```

To generate a first-20 predicted-vs-actual table and confusion matrix:

```bash
python3 scripts/analyze_predictions.py --predictions-csv results/phase1/crema_d_full/predictions.csv --output-dir results/phase1/crema_d_full/analysis --dataset crema_d
```

The analysis script writes:

- `predicted_vs_actual_first20.csv`
- `predicted_vs_actual_first20.md`
- `confusion_matrix.csv`
- `top_confusions.csv`
- `report.txt`

Single command for the mandatory Phase 1 checkpoint:

```bash
bash scripts/run_phase1_mandatory.sh
```

## Adapted Objective

The current Phase 1 objective is now the LegalMemoCMT-style multimodal emotion recognition benchmark study:

- multimodal emotion classification
- explicit fusion of text, audio, and video
- unimodal and multimodal ablations
- imbalance-aware training with weighted cross-entropy or focal loss
- benchmark comparison using MELD and CREMA-D
- MemoCMT-style module breakdown: SER, TER, CMT
- paper-style fusion comparison using CMT pooling variants

Useful training modes:

```bash
python3 -m src.train.train --manifest data/manifests/meld_train.csv --output-dir results/phase1/meld_weighted --loss-type weighted-ce
python3 -m src.train.train --manifest data/manifests/meld_train.csv --output-dir results/phase1/meld_focal --loss-type focal --focal-gamma 2.0
python3 -m src.train.train --manifest data/manifests/meld_train.csv --output-dir results/phase1/meld_text_only --modalities text --loss-type weighted-ce
```

Optional ablation suite:

```bash
bash scripts/run_phase1_ablations.sh
```

Optional MemoCMT-style suite and case study:

```bash
bash scripts/run_memocmt_style_suite.sh
bash scripts/run_meld_case_study.sh
```


## Video Modality Policy

Video is implemented in the codebase, but the paper-aligned Phase 1 story keeps it as an ablation-only stream. The main MemoCMT-style comparison uses text and audio.

Use the dedicated script for optional video-only experiments:

For the MELD ViT facial-cue extension, the recommended end-to-end launcher is:

```bash
bash scripts/run_meld_vit_facecue_suite.sh
```

That suite already runs the data-preparation, Fold 2 training/analysis, and Fold 4 training/analysis steps in order. If you use the suite, you do **not** need to run the individual `run_meld_vit_facecue_prepare.sh`, `run_meld_vit_facecue_fold2.sh`, `analyze_meld_vit_facecue_fold2.sh`, `run_meld_vit_facecue_fold4.sh`, or `analyze_meld_vit_facecue_fold4.sh` scripts separately. Keep `run_meld_vit_facecue_verify.sh` as an optional separate check if you want to confirm the manifest and folds before training.

In other words:

- `run_meld_vit_facecue_suite.sh` = full end-to-end run
- `run_meld_vit_facecue_verify.sh` = optional validation only
- the individual prepare/train/analyze scripts = manual control mode, not required when using the suite

```bash
bash scripts/run_video_ablation.sh
```

## Paper-Aligned Path

This is the closer MemoCMT-style implementation path using pretrained encoders, bidirectional cross-attention fusion, and MELD 5-fold CV:

```bash
bash scripts/run_paper_aligned_meld_cv.sh
bash scripts/run_paper_aligned_suite.sh
bash scripts/run_paper_aligned_case_study.sh
```

Key settings used by the paper-aligned path:

- `--encoder-mode pretrained`
- `--encoder-mode paper` is also supported and uses the same pretrained encoders
- fold-generated train and validation manifests for MELD CV
- `--split test` for final held-out evaluation
- `--modalities text,audio` for SER/TER/CMT core experiments
- `--fusion-pooling cls|mean|max|min`
- `--fusion-pooling min` is the paper's best MELD setting

The paper-aligned path uses:

- pretrained text encoder: `bert-base-uncased`
- pretrained speech encoder: `facebook/hubert-base-ls960`
- bidirectional cross-attention CMT for text/audio fusion
- fold-level train/dev CV plus a held-out test split for final reporting
- held-out test prediction export and confusion analysis
- MELD 5-fold cross-validation over train/dev dialogues, with the official MELD test split held out for final reporting

For per-sample predicted vs actual inspection, use:

```bash
python3 scripts/export_predictions.py --manifest data/manifests/meld_train.csv --checkpoint results/phase1/meld_full/best_model.pt --output-csv results/phase1/meld_full/predictions.csv
```

To create a MELD summary table and confusion matrix:

```bash
python3 scripts/export_predictions.py --manifest data/manifests/meld_test.csv --split test --checkpoint results/phase1/meld_full/best_model.pt --output-csv results/phase1/meld_full/predictions_test.csv
python3 scripts/analyze_predictions.py --predictions-csv results/phase1/meld_full/predictions_test.csv --output-dir results/phase1/meld_full/analysis_test --dataset meld
```

Preferred held-out wrapper:

```bash
bash scripts/export_predictions_from_eval.sh data/manifests/meld_test.csv results/phase1/meld_full/best_model.pt results/phase1/meld_full/predictions_test.csv test
```

These outputs are useful for the case study and the comparison/discussion section of the report.

For the paper-aligned MELD run, the main entrypoint is:

```bash
bash scripts/run_paper_aligned_meld_cv.sh
```

That script:

- rebuilds `data/manifests/meld_raw.csv`
- creates 5 dialogue-grouped MELD folds under `data/manifests/meld_cv/`
- trains the `CMT + MIN` paper-aligned model on each fold
- evaluates each fold on the held-out MELD test split
- aggregates per-fold metrics into `results/paper_aligned_meld_cv/cmt_min/summary.json`

Use `bash scripts/run_paper_aligned_case_study.sh` only if you want the older pooling ablation comparison on a single MELD held-out split. The CV runner above is the primary paper-aligned MELD workflow.

## Next implementation steps

1. Use the new MELD 5-fold CV workflow as the paper-aligned default.
2. Re-run the MELD case study ablations if you want pooling comparisons on the new bidirectional CMT branch.
3. Add or refresh analysis notebooks against the fold-level predictions.
4. Keep CREMA-D as the second benchmark and defer IEMOCAP.
