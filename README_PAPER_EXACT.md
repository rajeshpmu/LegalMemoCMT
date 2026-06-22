# Paper Exact Protocol

This document describes the paper-exact MemoCMT-style workflow that is being prepared for the project. It is separate from the current pragmatic paper-aligned runs and is meant to match the base paper as closely as the current repo structure allows.

## What This Protocol Is

The exact paper target for MELD is:

- BERT for text
- HuBERT for audio
- bidirectional cross-attention CMT
- MIN pooling for the MELD headline result
- 5-fold cross-validation over MELD train/dev dialogues
- held-out MELD test evaluation for each fold

The paper also describes:

- Adam optimizer
- learning rate `1e-4`
- `beta1 = 0.9`
- `beta2 = 0.999`
- step learning-rate decay by `0.1` every `30` epochs
- training up to `100` epochs with best validation checkpoint selection

## Why This Is Separate From the Current Paper-Aligned Workflow

The current working scripts in the repository were optimized to get the project moving and to keep runs manageable. The paper-exact protocol is stricter:

- the main MELD result should be `CMT + MIN`
- the schedule should follow the paper more closely
- the run should be treated as the primary paper-aligned benchmark result

This separate README keeps the exact protocol explicit and avoids mixing it with the earlier exploratory pooling runs.

## Recommended Scripts

Primary exact MELD workflow:

```bash
bash scripts/run_paper_exact_meld_cv.sh
```

Optional exact pooling sweep:

```bash
bash scripts/run_paper_exact_meld_pooling_sweep.sh
```

## Current Status

The scripts are created but have not been executed yet. They are ready to use when you decide to switch from the current pragmatic runs to the stricter paper-exact protocol.

## What To Expect From The Outputs

The exact MELD CV runner will write outputs under:

- `results/paper_exact_meld_cv/cmt_min/`

It will create:

- fold-level checkpoints
- fold-level `metrics.json`
- fold-level `predictions_test.csv`
- aggregated `summary.json`
- aggregated `summary.md`

The pooling sweep will write outputs under:

- `results/paper_exact_meld_sweep/`

## How This Should Be Interpreted

Use the `paper_exact` scripts when you want the strictest reproducibility story relative to the base paper.

Use the current `paper_aligned` scripts when you want a working, already-validated path for experimentation and analysis.

The key distinction is:

- `paper_aligned` = pragmatic, runnable project path
- `paper_exact` = stricter protocol intended to match the base paper as closely as possible

## Notes For Later Execution

When you are ready to run the exact protocol, confirm that the training loop uses the paper schedule:

- 100 epochs
- step LR decay every 30 epochs
- best checkpoint based on validation

The scripts are prepared for that exact workflow.
