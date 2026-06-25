#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

SCOTUS_INDEX="${SCOTUS_INDEX:-$ROOT_DIR/data/phase2/scotus/index/scotus_transcripts.csv}"
TRIBUNAL_INDEX="${TRIBUNAL_INDEX:-$ROOT_DIR/data/phase2/tribunal_records/index/tribunal_records.csv}"
TRIBUNAL_SOURCES="${TRIBUNAL_SOURCES:-$ROOT_DIR/data/phase2/source_manifests/tribunal_sources_target_dataset.csv}"
WITNESS_MANIFEST="${WITNESS_MANIFEST:-$ROOT_DIR/data/phase2/source_manifests/witness_harvest_manifest.csv}"
PHASE2_SPLIT_MANIFEST="${PHASE2_SPLIT_MANIFEST:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv}"
INIT_CKPT="${INIT_CKPT:-$ROOT_DIR/results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt}"

echo "Phase 2 RunPod readiness check"
echo "Repository root: $ROOT_DIR"
echo

"$PYTHON_BIN" - <<'PY' "$SCOTUS_INDEX" "$TRIBUNAL_INDEX" "$TRIBUNAL_SOURCES" "$WITNESS_MANIFEST" "$PHASE2_SPLIT_MANIFEST" "$INIT_CKPT"
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

scotus_index = Path(sys.argv[1])
tribunal_index = Path(sys.argv[2])
tribunal_sources = Path(sys.argv[3])
witness_manifest = Path(sys.argv[4])
split_manifest = Path(sys.argv[5])
checkpoint = Path(sys.argv[6])

def report(path: Path, label: str) -> bool:
    ok = path.exists()
    print(f"{label}: {'OK' if ok else 'MISSING'} -> {path}")
    return ok

scotus_ok = report(scotus_index, "scotus_index")
tribunal_ok = report(tribunal_index, "tribunal_index")
source_ok = report(tribunal_sources, "tribunal_sources")
witness_ok = report(witness_manifest, "witness_manifest")
split_ok = report(split_manifest, "phase2_split_manifest")
ckpt_ok = report(checkpoint, "warm_start_checkpoint")

if source_ok:
    tri_df = pd.read_csv(tribunal_sources)
    print(f"tribunal_sources rows: {len(tri_df)}")
if witness_ok:
    wit_df = pd.read_csv(witness_manifest)
    print(f"witness_manifest rows: {len(wit_df)}")
if scotus_ok:
    scotus_df = pd.read_csv(scotus_index)
    print(f"scotus_index rows: {len(scotus_df)}")
if tribunal_ok:
    tribunal_df = pd.read_csv(tribunal_index)
    print(f"tribunal_index rows: {len(tribunal_df)}")
if split_ok:
    split_df = pd.read_csv(split_manifest)
    print(f"phase2_split_manifest rows: {len(split_df)}")
    print(f"phase2_split_manifest splits: {split_df['split'].value_counts(dropna=False).to_dict() if 'split' in split_df.columns else 'split column missing'}")

print()
print("Eyewitness incongruence paper: reference only, not required for readiness.")
print("Phase 2 can fine-tune only when the split manifest and warm-start checkpoint are both present.")

if not (scotus_ok and tribunal_ok and source_ok and witness_ok and split_ok and ckpt_ok):
    raise SystemExit(1)
PY

echo
echo "Phase 2 RunPod readiness check complete."
