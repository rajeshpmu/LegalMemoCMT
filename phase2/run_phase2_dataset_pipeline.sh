#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
WITNESS_MANIFEST="${WITNESS_MANIFEST:-$ROOT_DIR/data/phase2/source_manifests/witness_harvest_manifest.csv}"
TRIBUNAL_SOURCES="${TRIBUNAL_SOURCES:-$ROOT_DIR/data/phase2/source_manifests/tribunal_sources_target_dataset.csv}"
RESOLVED_MANIFEST="${RESOLVED_MANIFEST:-$ROOT_DIR/data/resolved_manifest.csv}"
MATERIALIZED_MANIFEST="${MATERIALIZED_MANIFEST:-$ROOT_DIR/data/resolved_manifest_materialized.csv}"
RAW_TRANSCRIPTS="${RAW_TRANSCRIPTS:-$ROOT_DIR/data/raw/transcripts}"
RAW_VIDEOS="${RAW_VIDEOS:-$ROOT_DIR/data/raw/videos}"
RAW_AUDIO="${RAW_AUDIO:-$ROOT_DIR/data/raw/audio}"
DATASET_CSV="${DATASET_CSV:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset.csv}"
REPORT_HTML="${REPORT_HTML:-$ROOT_DIR/reports/dataset_status.html}"

if [ -x /usr/bin/nvidia-smi ] || command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU detected, but dataset preparation remains CPU-bound. Training/evaluation wrappers will use CUDA."
fi

"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" validate-tri
"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" validate-witness
"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" resolve --witness-manifest "$WITNESS_MANIFEST" --output "$RESOLVED_MANIFEST"
"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" materialize --resolved-manifest "$RESOLVED_MANIFEST" --output "$MATERIALIZED_MANIFEST" --transcripts-dir "$RAW_TRANSCRIPTS" --videos-dir "$RAW_VIDEOS" --audio-dir "$RAW_AUDIO"

# The next commands assume the resolved manifest contains downloadable public URLs.
# They are kept here as the canonical end-to-end order and should be run only after
# the record discovery step is stable for the selected source rows.
"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" build-dataset --resolved-manifest "$MATERIALIZED_MANIFEST" --output-csv "$DATASET_CSV"
"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" weak-labels --dataset-csv "$DATASET_CSV" --output-dir "$ROOT_DIR/data/processed/phase2/weak_labels"
"$PYTHON_BIN" "$ROOT_DIR/phase2/dataset_builder.py" dashboard --dataset-csv "$DATASET_CSV" --resolved-manifest "$RESOLVED_MANIFEST" --output-html "$REPORT_HTML"

echo "Phase 2 dataset pipeline shell wrapper complete."
