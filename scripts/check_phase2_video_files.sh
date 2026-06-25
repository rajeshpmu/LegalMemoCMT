#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MANIFEST="${1:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_clean.csv}"

if [ ! -f "$MANIFEST" ]; then
  MANIFEST="$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv"
fi

echo "Phase 2 video file check"
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
if "video_path" not in df.columns:
    raise SystemExit("Manifest does not contain a video_path column")

video = df["video_path"].astype(str)
exists = video.map(lambda x: Path(x).exists() if x and x.lower() != "nan" else False)

print(f"Rows: {len(df)}")
print(f"Video files present: {int(exists.sum())}")
print(f"Video files missing: {int((~exists).sum())}")
print(f"Unique video paths: {video.nunique()}")
print(f"Coverage: {100.0 * exists.mean():.2f}%")
print()
print("Sample existing video rows:")
existing = df.loc[exists, ["utterance_id", "manifest_id", "video_path"]].head(5)
if existing.empty:
    print("(none)")
else:
    print(existing.to_string(index=False))
print()
print("Sample missing video rows:")
missing = df.loc[~exists, ["utterance_id", "manifest_id", "video_path"]].head(10)
if missing.empty:
    print("(none)")
else:
    print(missing.to_string(index=False))
PY

echo
echo "Phase 2 video file check complete."
