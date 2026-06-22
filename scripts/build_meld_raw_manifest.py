from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_meld_manifest import EMOTION_MAP, find_meld_clip
from src.data import normalize_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a MELD manifest that points at raw media clips")
    parser.add_argument("--meld-root", type=str, default="data/MELD", help="Path to MELD dataset root")
    parser.add_argument("--manifest-dir", type=str, default="data/manifests", help="Directory for output manifests")
    args = parser.parse_args()

    meld_root = Path(args.meld_root)
    ann_dir = meld_root / "annotations"
    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    skipped = 0
    for split in ["train", "dev", "test"]:
        csv_path = ann_dir / f"{split}_sent_emo.csv"
        if not csv_path.exists():
            print(f"Skipping {split}: missing {csv_path}")
            continue

        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            emotion = str(row["Emotion"]).strip().lower()
            if emotion not in EMOTION_MAP:
                continue
            dialogue_id = int(row["Dialogue_ID"])
            utterance_id = int(row["Utterance_ID"])
            transcript = normalize_text(str(row["Utterance"]))
            try:
                clip_path = find_meld_clip(meld_root / "raw", split, dialogue_id, utterance_id)
                sample_id = f"{split}_dia{dialogue_id}_utt{utterance_id}"
                rows.append(
                    {
                        "sample_id": sample_id,
                        "split": split,
                        "label": EMOTION_MAP[emotion],
                        "video_path": str(clip_path),
                        "audio_path": str(clip_path),
                        "transcript": transcript,
                    }
                )
            except Exception as exc:
                skipped += 1
                print(f"Skipping {split} dia{dialogue_id}_utt{utterance_id}: {exc}")

    out_csv = manifest_dir / "meld_raw.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Wrote {len(rows)} rows to {out_csv}")
    if skipped:
        print(f"Skipped {skipped} unreadable samples")


if __name__ == "__main__":
    main()
