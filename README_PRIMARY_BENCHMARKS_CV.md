# Primary Benchmark CV Workflow

This is the stricter benchmark split for the new approach.

## Required Before Running

Make sure the following are available before running any benchmark scripts:

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

Install them with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-phase1.txt
```

### Pretrained models

The scripts will download these Hugging Face backbones on first use if they are not already cached:

- `bert-base-uncased`
- `facebook/hubert-base-ls960`
- `google/vit-base-patch16-224-in21k`

### External tools / data

- MELD raw clips and annotations
- CREMA-D data if you run the speech-emotion benchmark
- A working video decoding backend through OpenCV
- Enough disk space for extracted features, checkpoints, and results

## Speech-Emotion Track

- Dataset: `CREMA-D`
- Protocol: speaker-independent 5-fold cross-validation
- Main metric names:
  - `W-Acc`
  - `UW-Acc`
- Scripts:
  - `scripts/build_crema_d_cv_folds.py`
  - `scripts/run_primary_speech_emotion_crema_d_cv.sh`
  - `scripts/run_primary_speech_emotion_crema_d_cv_analysis.sh`
  - `scripts/aggregate_crema_d_cv_metrics.py`

## Conversational Track

- Dataset: `MELD`
- Protocol: 5-fold dialogue-based cross-validation
- Main metric names:
  - `accuracy`
  - `weighted_f1`
  - `macro_f1`
- Scripts:
  - `scripts/run_primary_conversational_meld_cv.sh`
  - `scripts/run_primary_conversational_meld_analysis.sh`

## Notes

- The implementation code is unchanged.
- The new CREMA-D CV workflow is the more paper-like speech-emotion route.
- The MELD CV workflow remains the paper-aligned conversational route.
- For a clean start, run the CREMA-D CV script first, inspect its summary and analysis, then run the MELD CV script and compare the conversational result separately.
- In the CREMA-D summary, W-Acc is the same sample-accuracy style quantity used by the repo’s current metrics layer, and UW-Acc is the mean per-class accuracy over the observed classes.
- For the MELD ViT facial-cue path, the full suite launcher `bash scripts/run_meld_vit_facecue_suite.sh` already chains together the prepare/train/analyze steps. If you use that suite, you do not need to run the individual prepare, Fold 2, Fold 4, or analysis scripts separately. Keep `bash scripts/run_meld_vit_facecue_verify.sh` as a separate optional data check.
- In short: the suite is the end-to-end path, while the individual facial-cue scripts are only needed if you want to step through the pipeline manually for debugging or teaching.
