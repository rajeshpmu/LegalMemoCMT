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

import csv
import sys
from pathlib import Path

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
    with tribunal_sources.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tri_rows = list(reader)
        print(f"tribunal_sources rows: {len(tri_rows)}")
        print(f"tribunal_sources columns: {list(reader.fieldnames or [])}")

if witness_ok:
    with witness_manifest.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        wit_rows = list(reader)
        print(f"witness_manifest rows: {len(wit_rows)}")
        print(f"witness_manifest columns: {list(reader.fieldnames or [])}")

if scotus_ok:
    with scotus_index.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        scotus_rows = list(reader)
        print(f"scotus_index rows: {len(scotus_rows)}")
        print(f"scotus_index columns: {list(reader.fieldnames or [])}")

if tribunal_ok:
    with tribunal_index.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tribunal_rows = list(reader)
        print(f"tribunal_index rows: {len(tribunal_rows)}")
        print(f"tribunal_index columns: {list(reader.fieldnames or [])}")

print()
print("Eyewitness incongruence paper: reference only, not a required dataset.")
print("If you want to keep the PDF locally, verify the file separately where you store project references.")

if not (scotus_ok and tribunal_ok and source_ok and witness_ok):
    raise SystemExit(1)
PY

echo
echo "Phase 2 source readiness check complete."
