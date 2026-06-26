#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${1:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_tri_modal.csv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

if [ ! -f "$MANIFEST" ]; then
  MANIFEST="$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv"
fi

echo "Phase 2 video integrity check"
echo "Repository root: $ROOT_DIR"
echo "Manifest: $MANIFEST"
echo

"$PYTHON_BIN" - <<'PY' "$MANIFEST"
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

manifest = Path(sys.argv[1])
if not manifest.exists():
    raise SystemExit(f"Manifest not found: {manifest}")

df = pd.read_csv(manifest)
if "video_path" not in df.columns:
    raise SystemExit("Manifest does not contain a video_path column")

def check_video(path_str: object) -> tuple[bool, str]:
    text = str(path_str or "").strip()
    if not text or text.lower() == "nan":
        return False, "missing"
    p = Path(text)
    if not p.exists():
        return False, "missing"
    try:
        file_out = subprocess.run(["file", str(p)], check=True, capture_output=True, text=True).stdout.strip()
        if "HTML document" in file_out or "ASCII text" in file_out:
            return False, file_out
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", str(p)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, probe.stdout.strip() or "ok"
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or "").strip()
        return False, msg or "ffprobe failed"

results = df["video_path"].map(check_video)
ok = results.map(lambda x: bool(x[0]))
details = results.map(lambda x: x[1])

print(f"Rows: {len(df)}")
print(f"Valid video files: {int(ok.sum())}")
print(f"Invalid video files: {int((~ok).sum())}")
print(f"Coverage: {100.0 * ok.mean():.2f}%")

bad_rows = df.loc[~ok, ["utterance_id", "manifest_id", "video_path"]].copy()
bad_rows["reason"] = details[~ok].values
print()
print("Sample invalid video rows:")
if bad_rows.empty:
    print("(none)")
else:
    print(bad_rows.head(10).to_string(index=False))
PY

echo
echo "Phase 2 video integrity check complete."
