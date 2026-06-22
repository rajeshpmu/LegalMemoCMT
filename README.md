# LegalMemoCMT

LegalMemoCMT is a multimodal emotion recognition project for courtroom testimony analysis. The codebase supports text, audio, and video-style experiments, with MELD as the main conversational benchmark and CREMA-D as the speech-emotion benchmark.

## Before You Run Any Scripts

Install the Python environment from `requirements-phase1.txt` and make sure the required pretrained model backbones can be downloaded or are already cached locally.

### Python packages

Required packages include:

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

### Pretrained model downloads

The scripts will download these Hugging Face backbones on first use if they are not already cached:

- `bert-base-uncased` for text
- `facebook/hubert-base-ls960` for audio
- `google/vit-base-patch16-224-in21k` for the MELD facial-cue / ViT path

For offline work, download them once while you have network access and keep the local cache.

### External tools and data

- Python 3.11+ recommended
- MELD raw clips and annotations
- CREMA-D manifest/data if you run the speech-emotion benchmark
- Enough disk space for extracted features, checkpoints, and result folders
- A working video decoding backend such as OpenCV

## Where to Start

- [Phase 1 overview](README_PHASE1.md)
- [Primary benchmark CV workflow](README_PRIMARY_BENCHMARKS_CV.md)
- [New benchmark approach](README_NEW_BENCHMARK_APPROACH.md)
- For the MELD ViT facial-cue path, use `bash scripts/run_meld_vit_facecue_suite.sh` once you are ready to run the full prepare/train/analyze sequence end to end. That suite already runs prepare, Fold 2, Fold 4, and both analyses, so you do not need to run those individual scripts separately.
- If you want to inspect the data before training, run `bash scripts/run_meld_vit_facecue_verify.sh` separately.
