#!/usr/bin/env bash
set -euo pipefail

# Optional until the small-run validation is stable and you are ready for a longer execution.

echo "Run only after the small-run workflow is validated."
echo "Current project policy: this is OPTIONAL, not mandatory."

python3 -m src.train.train --manifest data/manifests/meld_train.csv --output-dir results/phase1/meld_full --loss-type weighted-ce
python3 -m src.train.train --manifest data/manifests/crema_d.csv --output-dir results/phase1/crema_d_full --loss-type weighted-ce
