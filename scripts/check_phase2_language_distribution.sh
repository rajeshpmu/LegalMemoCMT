#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
MANIFEST="${1:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_clean.csv}"
TEXT_COLUMN="${TEXT_COLUMN:-utterance_text}"

if [ ! -f "$MANIFEST" ]; then
  MANIFEST="$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split.csv"
fi

echo "Phase 2 language distribution check"
echo "Repository root: $ROOT_DIR"
echo "Manifest: $MANIFEST"
echo "Text column: $TEXT_COLUMN"
echo

"$PYTHON_BIN" - <<'PY' "$MANIFEST" "$TEXT_COLUMN"
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

manifest = Path(sys.argv[1])
text_column = sys.argv[2]

if not manifest.exists():
    raise SystemExit(f"Manifest not found: {manifest}")

df = pd.read_csv(manifest)
if text_column not in df.columns and "transcript" not in df.columns and "utterance_text" not in df.columns and "text" not in df.columns:
    raise SystemExit(f"Manifest does not contain any usable text column: {text_column}")

if text_column not in df.columns:
    if "utterance_text" in df.columns:
        text_column = "utterance_text"
    elif "transcript" in df.columns:
        text_column = "transcript"
    else:
        text_column = "text"

def classify(text: object) -> str:
    s = str(text or "").strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return "other"
    has_latin = any("A" <= ch <= "Z" or "a" <= ch <= "z" for ch in s)
    has_dev = any("\u0900" <= ch <= "\u097F" for ch in s)
    has_other_alpha = any(ch.isalpha() and not (("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("\u0900" <= ch <= "\u097F")) for ch in s)
    if has_latin and has_dev:
        return "mixed"
    if has_latin:
        return "english"
    if has_dev:
        return "devanagari"
    if has_other_alpha:
        return "other"
    return "other"

classes = df[text_column].map(classify)
total = len(df)
counts = classes.value_counts(dropna=False).to_dict()

english = int(counts.get("english", 0))
devanagari = int(counts.get("devanagari", 0))
other = int(counts.get("other", 0))
mixed = int(counts.get("mixed", 0))

def pct(n: int) -> float:
    return 100.0 * n / total if total else 0.0

print(f"Rows: {total}")
print(f"English share: {pct(english):.2f}% ({english})")
print(f"Devanagari share: {pct(devanagari):.2f}% ({devanagari})")
print(f"Other-script share: {pct(other):.2f}% ({other})")
print(f"Mixed-language rows: {mixed}")

if mixed > 0 or (devanagari > 0 and english > 0) or other > 0:
    print("Warning: mixed or non-English script content detected in the Phase 2 manifest.")
    if mixed > 0:
        print("  Mixed-language rows are present and should be inspected before training.")
    if devanagari > 0 and english > 0:
        print("  English and Devanagari both appear in the corpus.")
    if other > 0:
        print("  Other-script rows are present and should be reviewed.")
else:
    print("No unexpected mixed-language content detected.")

sample_mixed = df.loc[classes.eq("mixed"), [c for c in ["utterance_id", "manifest_id", text_column] if c in df.columns]].head(5)
if not sample_mixed.empty:
    print()
    print("Sample mixed-language rows:")
    print(sample_mixed.to_string(index=False))
PY

echo
echo "Phase 2 language distribution check complete."
