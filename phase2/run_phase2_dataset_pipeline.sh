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

if [ ! -f "$TRIBUNAL_SOURCES" ]; then
  echo "Missing Phase 2 source manifest: $TRIBUNAL_SOURCES" >&2
  exit 1
fi

if [ ! -f "$WITNESS_MANIFEST" ]; then
  echo "Missing Phase 2 witness manifest: $WITNESS_MANIFEST" >&2
  exit 1
fi

if [ "${ALLOW_PLACEHOLDER_WITNESS_MANIFEST:-0}" != "1" ]; then
  if "$PYTHON_BIN" - <<'PY' "$WITNESS_MANIFEST"
from __future__ import annotations

import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

def _norm(value: object) -> str:
    return str(value or "").strip().lower()

placeholder_rows = 0
for row in rows:
    transcript_url = _norm(row.get("transcript_url"))
    video_url = _norm(row.get("video_url"))
    hearing_date = _norm(row.get("hearing_date"))
    witness_name = _norm(row.get("witness_name"))
    notes = _norm(row.get("notes"))
    if (
        not hearing_date
        and (not witness_name or witness_name in {"", "unknown", "placeholder"})
        and (transcript_url in {"", "https://ucr.irmct.org/", "http://ucr.irmct.org/"})
        and (video_url in {"", "https://ucr.irmct.org/", "http://ucr.irmct.org/"})
        and "populate from ucr search" in notes
    ):
        placeholder_rows += 1

if rows and placeholder_rows == len(rows):
    raise SystemExit(1)
PY
  then
    :
  else
    echo "Phase 2 witness manifest is still a placeholder. Do not use it for downloads until real hearing rows and resolved record links exist." >&2
    echo "Set ALLOW_PLACEHOLDER_WITNESS_MANIFEST=1 only if you explicitly want to override this guard." >&2
    exit 1
  fi
fi

echo "Phase 2 dataset pipeline"
echo "Status note: the source CSVs are planning manifests only; the final dataset is produced later after record resolution, materialization, segmentation, and audio/video extraction."
echo "Source manifests:"
echo "  tribunal sources: $TRIBUNAL_SOURCES"
echo "  witness manifest: $WITNESS_MANIFEST"
echo "Derived outputs:"
echo "  resolved manifest: $RESOLVED_MANIFEST"
echo "  materialized manifest: $MATERIALIZED_MANIFEST"
echo "  dataset csv: $DATASET_CSV"
echo "  weak labels: $ROOT_DIR/data/processed/phase2/weak_labels"
echo "  report html: $REPORT_HTML"
echo

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
