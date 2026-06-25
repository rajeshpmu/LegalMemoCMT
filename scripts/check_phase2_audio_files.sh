#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MANIFEST="${1:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_clean.csv}"

if [ ! -f "$MANIFEST" ]; then
  MANIFEST="$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv"
fi

echo "Phase 2 audio file check"
echo "Repository root: $ROOT_DIR"
echo "Manifest: $MANIFEST"
echo

"$PYTHON_BIN" - <<'PY' "$MANIFEST"
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

manifest = Path(sys.argv[1])
if not manifest.exists():
    raise SystemExit(f"Manifest not found: {manifest}")

df = pd.read_csv(manifest)
if "audio_path" not in df.columns:
    raise SystemExit("Manifest does not contain an audio_path column")

audio = df["audio_path"].astype(str)
exists = audio.map(lambda x: Path(x).exists() if x and x.lower() != "nan" else False)

print(f"Rows: {len(df)}")
print(f"Audio files present: {int(exists.sum())}")
print(f"Audio files missing: {int((~exists).sum())}")
print(f"Unique audio paths: {audio.nunique()}")
print(f"Coverage: {100.0 * exists.mean():.2f}%")
print()
print("Sample existing audio rows:")
existing = df.loc[exists, ["utterance_id", "manifest_id", "audio_path"]].head(5)
if existing.empty:
    print("(none)")
else:
    print(existing.to_string(index=False))
print()
print("Sample missing audio rows:")
missing = df.loc[~exists, ["utterance_id", "manifest_id", "audio_path"]].head(10)
if missing.empty:
    print("(none)")
else:
    print(missing.to_string(index=False))
PY

echo
echo "Phase 2 audio file check complete."
