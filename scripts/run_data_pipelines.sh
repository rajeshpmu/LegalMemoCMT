#!/usr/bin/env bash
set -euo pipefail

# Phase 1 data pipeline runner.
# IEMOCAP is intentionally commented out because it is not part of the current plan.

python3 scripts/download_meld.py --output data/MELD --annotations --raw --extract
python3 scripts/build_meld_manifest.py --meld-root data/MELD --output-root data/processed/MELD --manifest-dir data/manifests
python3 scripts/validate_manifest.py --manifest data/manifests/meld_train.csv --strict-exists

# CREMA-D is the public replacement benchmark for the deferred IEMOCAP slot.
python3 scripts/download_crema_d.py --output data/CREMA_D
# Run this after cloning the CREMA-D repository with git lfs.
# python3 scripts/build_crema_d_labels.py --crema-repo data/CREMA_D_repo --output-csv data/CREMA_D/labels.csv
# Once labels.csv exists, build the manifest.
# python3 scripts/build_crema_d_manifest.py --crema-root data/CREMA_D --manifest-dir data/manifests --labels-csv data/CREMA_D/labels.csv
# python3 scripts/validate_manifest.py --manifest data/manifests/crema_d.csv --strict-exists

# IEMOCAP is deferred for now and should not be run in the current workflow.
# python3 scripts/build_iemocap_manifest.py --iemocap-root data/IEMOCAP --output-root data/processed/IEMOCAP --manifest-dir data/manifests
