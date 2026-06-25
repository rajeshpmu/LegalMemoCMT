#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

SCOTUS_INDEX="${SCOTUS_INDEX:-$ROOT_DIR/data/phase2/scotus/index/scotus_transcripts.csv}"
TRIBUNAL_INDEX="${TRIBUNAL_INDEX:-$ROOT_DIR/data/phase2/tribunal_records/index/tribunal_records.csv}"
TRIBUNAL_SOURCES="${TRIBUNAL_SOURCES:-$ROOT_DIR/data/phase2/source_manifests/tribunal_sources_target_dataset.csv}"
WITNESS_MANIFEST="${WITNESS_MANIFEST:-$ROOT_DIR/data/phase2/source_manifests/witness_harvest_manifest.csv}"

echo "Phase 2 source readiness check"
echo "Repository root: $ROOT_DIR"
echo

"$PYTHON_BIN" - <<'PY' "$SCOTUS_INDEX" "$TRIBUNAL_INDEX" "$TRIBUNAL_SOURCES" "$WITNESS_MANIFEST"
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

scotus_index = Path(sys.argv[1])
tribunal_index = Path(sys.argv[2])
tribunal_sources = Path(sys.argv[3])
witness_manifest = Path(sys.argv[4])

def report(path: Path, label: str) -> bool:
    ok = path.exists()
    print(f"{label}: {'OK' if ok else 'MISSING'} -> {path}")
    return ok

scotus_ok = report(scotus_index, "scotus_index")
tribunal_ok = report(tribunal_index, "tribunal_index")
source_ok = report(tribunal_sources, "tribunal_sources")
witness_ok = report(witness_manifest, "witness_manifest")

if source_ok:
    tri_df = pd.read_csv(tribunal_sources)
    print(f"tribunal_sources rows: {len(tri_df)}")
    print(f"tribunal_sources columns: {list(tri_df.columns)}")

if witness_ok:
    wit_df = pd.read_csv(witness_manifest)
    print(f"witness_manifest rows: {len(wit_df)}")
    print(f"witness_manifest columns: {list(wit_df.columns)}")

if scotus_ok:
    scotus_df = pd.read_csv(scotus_index)
    print(f"scotus_index rows: {len(scotus_df)}")
    print(f"scotus_index columns: {list(scotus_df.columns)}")

if tribunal_ok:
    tribunal_df = pd.read_csv(tribunal_index)
    print(f"tribunal_index rows: {len(tribunal_df)}")
    print(f"tribunal_index columns: {list(tribunal_df.columns)}")

print()
print("Eyewitness incongruence paper: reference only, not a required dataset.")
print("If you want to keep the PDF locally, verify the file separately where you store project references.")

if not (scotus_ok and tribunal_ok and source_ok and witness_ok):
    raise SystemExit(1)
PY

echo
echo "Phase 2 source readiness check complete."
