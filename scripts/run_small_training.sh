#!/usr/bin/env bash
set -euo pipefail

# Small-run Phase 1 training workflow.
# This is meant to validate the full pipeline before a full benchmark run.

mkdir -p data/manifests results/phase1_small

# MELD small run
python3 scripts/create_subset_manifest.py --manifest data/manifests/meld_train.csv --output data/manifests/meld_train_small.csv --per-split 100
python3 -m src.train.train --manifest data/manifests/meld_train_small.csv --output-dir results/phase1_small/meld

# CREMA-D small run
python3 scripts/create_subset_manifest.py --manifest data/manifests/crema_d.csv --output data/manifests/crema_d_small.csv --per-split 100
python3 -m src.train.train --manifest data/manifests/crema_d_small.csv --output-dir results/phase1_small/crema_d

# IEMOCAP remains deferred.
