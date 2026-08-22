#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

PHASE2_MANIFEST="${PHASE2_MANIFEST:-$ROOT_DIR/data/processed/phase2/legalmemocmt_phase2_dataset_split_tri_modal.csv}"
INIT_CKPT="${INIT_CKPT:-$ROOT_DIR/results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt}"

echo "Phase 2 fine-tuning readiness check"
echo "Repository root: $ROOT_DIR"
echo

"$PYTHON_BIN" - <<'PY' "$PHASE2_MANIFEST" "$INIT_CKPT"
from __future__ import annotations

import csv
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
ckpt = Path(sys.argv[2])

if not manifest.exists():
    raise SystemExit(f"Phase 2 training manifest not found: {manifest}")
if not ckpt.exists():
    raise SystemExit(f"Warm-start checkpoint not found: {ckpt}")

with manifest.open(newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    columns = list(reader.fieldnames or [])
    rows = [{k: "" if v is None else str(v) for k, v in row.items()} for row in reader]

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
missing_cols = required_cols - set(columns)
if missing_cols:
    raise SystemExit(f"Phase 2 manifest is missing columns: {sorted(missing_cols)}")

split_counts: dict[str, int] = {}
for row in rows:
    split = row.get("split", "")
    split_counts[split] = split_counts.get(split, 0) + 1

audio_present = sum(1 for row in rows if str(row.get("audio_path") or "").strip())
video_present = sum(1 for row in rows if str(row.get("video_path") or "").strip())
audio_coverage = 100.0 * audio_present / max(len(rows), 1)
video_coverage = 100.0 * video_present / max(len(rows), 1)

print(f"Phase 2 manifest: {manifest}")
print(f"Rows: {len(rows)}")
print(f"Splits: {split_counts}")
print(f"Video coverage: {video_coverage:.2f}%")
print(f"Audio coverage: {audio_coverage:.2f}%")
print(f"Checkpoint: {ckpt}")
print("raw_meld_needed: False if this checkpoint already exists")
print("raw_meld_needed: only needed again if you want to rebuild the warm-start checkpoint from scratch")

if audio_present == 0:
    raise SystemExit("Phase 2 fine-tuning blocked until audio extraction is complete")
if video_present == 0:
    raise SystemExit("Phase 2 fine-tuning blocked until video coverage is present")
PY

echo
echo "Phase 2 fine-tuning readiness check complete."
