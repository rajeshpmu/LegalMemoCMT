#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

TRIBUNAL_SOURCES="${TRIBUNAL_SOURCES:-$ROOT_DIR/data/phase2/source_manifests/tribunal_sources_target_dataset.csv}"
WITNESS_MANIFEST="${WITNESS_MANIFEST:-$ROOT_DIR/data/phase2/source_manifests/witness_harvest_manifest.csv}"
RESOLVED_MANIFEST="${RESOLVED_MANIFEST:-$ROOT_DIR/data/resolved_manifest.csv}"
MATERIALIZED_MANIFEST="${MATERIALIZED_MANIFEST:-$ROOT_DIR/data/resolved_manifest_materialized.csv}"
DATASET_CSV="${DATASET_CSV:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset.csv}"
WEAK_LABELS_DIR="${WEAK_LABELS_DIR:-$ROOT_DIR/data/processed/phase2/weak_labels}"
REPORT_HTML="${REPORT_HTML:-$ROOT_DIR/reports/dataset_status.html}"

echo "Phase 2 dataset readiness check"
echo "Repository root: $ROOT_DIR"
echo

"$PYTHON_BIN" - <<'PY' "$TRIBUNAL_SOURCES" "$WITNESS_MANIFEST" "$RESOLVED_MANIFEST" "$MATERIALIZED_MANIFEST" "$DATASET_CSV" "$WEAK_LABELS_DIR" "$REPORT_HTML"
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

tribunal_sources = Path(sys.argv[1])
witness_manifest = Path(sys.argv[2])
resolved_manifest = Path(sys.argv[3])
materialized_manifest = Path(sys.argv[4])
dataset_csv = Path(sys.argv[5])
weak_labels_dir = Path(sys.argv[6])
report_html = Path(sys.argv[7])

required_files = {
    "tribunal_sources": tribunal_sources,
    "witness_manifest": witness_manifest,
    "resolved_manifest": resolved_manifest,
    "materialized_manifest": materialized_manifest,
    "dataset_csv": dataset_csv,
    "weak_labels_dir": weak_labels_dir,
    "report_html": report_html,
}

for name, path in required_files.items():
    if name == "weak_labels_dir":
        print(f"{name}: {'OK' if path.exists() and path.is_dir() else 'MISSING'} -> {path}")
    else:
        print(f"{name}: {'OK' if path.exists() else 'MISSING'} -> {path}")

if not tribunal_sources.exists() or not witness_manifest.exists():
    raise SystemExit("Phase 2 source manifests are missing.")

for label, path in [("tribunal_sources", tribunal_sources), ("witness_manifest", witness_manifest)]:
    df = pd.read_csv(path)
    print(f"{label} rows: {len(df)}")
    print(f"{label} columns: {list(df.columns)}")

if resolved_manifest.exists():
    resolved_df = pd.read_csv(resolved_manifest)
    print(f"resolved_manifest rows: {len(resolved_df)}")
    print(f"resolved_manifest columns: {list(resolved_df.columns)}")

if materialized_manifest.exists():
    materialized_df = pd.read_csv(materialized_manifest)
    print(f"materialized_manifest rows: {len(materialized_df)}")
    print(f"materialized_manifest columns: {list(materialized_df.columns)}")

dataset_ready = dataset_csv.exists()
print(f"dataset_ready: {dataset_ready}")
print("raw_meld_needed: False for Phase 2 dataset readiness")
print("raw_meld_needed: only the Phase 2 source manifests and derived artifacts are checked here")

if dataset_ready:
    dataset_df = pd.read_csv(dataset_csv)
    required_cols = {
        "utterance_id",
        "manifest_id",
        "tribunal",
        "case_name",
        "speaker_role",
        "speaker_name",
        "utterance_text",
        "start_time",
        "end_time",
        "video_path",
        "audio_path",
        "emotion_label",
        "credibility_label",
        "question_type",
        "cross_examination_flag",
    }
    missing_cols = required_cols - set(dataset_df.columns)
    if missing_cols:
        raise SystemExit(f"Phase 2 dataset CSV is missing columns: {sorted(missing_cols)}")
    print(f"dataset_rows: {len(dataset_df)}")
    print(f"dataset_splits: {dataset_df['split'].value_counts(dropna=False).to_dict() if 'split' in dataset_df.columns else 'split column not present'}")
    print(f"dataset_columns: {list(dataset_df.columns)}")

if not report_html.exists():
    print("dataset dashboard: MISSING")
if not weak_labels_dir.exists():
    print("weak labels directory: MISSING")
PY

echo
echo "Phase 2 dataset readiness check complete."
