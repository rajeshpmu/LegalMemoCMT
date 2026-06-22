# LegalMemoCMT First Submission Checklist

## What to submit

- `submission_first/` as the code package, or `submission_first.zip` if your submission portal expects a single archive.
- The code package includes:
  - `src/`
  - `scripts/`
  - `README_PHASE1.md`
  - `README_PAPER_EXACT.md`
  - `requirements-phase1.txt`

## What is intentionally excluded

- Raw datasets under `data/`
- Generated results under `results/`
- Mermaid artifacts under `artifacts/`
- Python cache folders (`__pycache__`)
- Temporary Office lock files (`~$*.docx`)

## Recommended first-submission focus

- Explain the code structure clearly
- Show that the data pipeline works
- Show the training and evaluation entry points
- Include the paper-aligned runner guide if the evaluator needs operational instructions
- Keep the submission compact and reproducible

## Main code entry points

- Training:
  - `python3 -m src.train.train`
- Evaluation:
  - `python3 -m src.train.evaluate`
- Prediction export:
  - `python3 scripts/export_predictions.py`
- Prediction analysis:
  - `python3 scripts/analyze_predictions.py`
- Paper-aligned MELD case study:
  - `bash scripts/run_paper_aligned_case_study.sh`
- Paper-aligned full suite:
  - `bash scripts/run_paper_aligned_suite.sh`

## How to run the code in a first submission environment

1. Install the required packages listed in `requirements-phase1.txt`.
2. Make sure the repository root is the working directory.
3. Run one of the paper-aligned scripts or a direct Python entry point.
4. Check the `results/` directory for saved checkpoints and metric files.

## What to expect after running

- Training logs printed per epoch.
- A saved `best_model.pt` checkpoint in the selected output folder.
- A `metrics.json` file from the evaluation step.
- Optional `predictions.csv`, confusion matrix files, and short analysis tables if the prediction-analysis scripts are used.
- For the paper-aligned runs, separate output folders per variant or per dataset.

## If you need a short explanation for the submission

This first submission contains the LegalMemoCMT codebase for multimodal emotion recognition, including the data loaders, model definitions, and training/evaluation scripts needed to run the project.
