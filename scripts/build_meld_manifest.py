from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import PreprocessConfig, extract_video_features, load_audio_features, normalize_text


EMOTION_MAP = {
    "neutral": 0,
    "joy": 1,
    "surprise": 2,
    "sadness": 3,
    "anger": 4,
    "fear": 5,
    "disgust": 6,
}


def find_meld_clip(raw_root: Path, split: str, dialogue_id: int, utterance_id: int) -> Path:
    clip_name = f"dia{dialogue_id}_utt{utterance_id}.mp4"
    split_dirs = {
        "train": ["train/train_splits", "train", "MELD.Raw/train/train_splits"],
        "dev": ["dev/dev_splits_complete", "dev", "MELD.Raw/dev/dev_splits_complete"],
        "test": ["test/output_repeated_splits_test", "test", "MELD.Raw/test/output_repeated_splits_test"],
    }.get(split, [split])

    candidates = [
        raw_root / rel / clip_name for rel in split_dirs
    ] + [
        raw_root / rel / "video" / clip_name for rel in split_dirs
    ] + [
        raw_root / clip_name,
        raw_root / "raw" / split / clip_name,
    ]
    for candidate in candidates:
        if candidate.is_file() and not candidate.name.startswith("._"):
            return candidate

    for candidate in raw_root.rglob(clip_name):
        if candidate.is_file() and not candidate.name.startswith("._") and split in str(candidate):
            return candidate

    raise FileNotFoundError(f"Could not locate MELD clip {clip_name} under {raw_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a MELD manifest with extracted features")
    parser.add_argument("--meld-root", type=str, default="data/MELD", help="Path to MELD dataset root")
    parser.add_argument("--output-root", type=str, default="data/processed/MELD", help="Output directory for features")
    parser.add_argument("--manifest-dir", type=str, default="data/manifests", help="Directory for output manifests")
    parser.add_argument("--frame-size", type=int, default=224)
    parser.add_argument("--num-frames", type=int, default=32)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--max-audio-seconds", type=float, default=10.0)
    args = parser.parse_args()

    meld_root = Path(args.meld_root)
    ann_dir = meld_root / "annotations"
    output_root = Path(args.output_root)
    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    cfg = PreprocessConfig(frame_size=args.frame_size, num_frames=args.num_frames, sample_rate=args.sample_rate, max_audio_seconds=args.max_audio_seconds)

    manifests = []
    for split in ["train", "dev", "test"]:
        csv_path = ann_dir / f"{split}_sent_emo.csv"
        if not csv_path.exists():
            print(f"Skipping {split}: missing {csv_path}")
            continue

        df = pd.read_csv(csv_path)
        rows = []
        skipped = 0
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
                feat_dir = output_root / split
                video_feat_path = feat_dir / "video" / f"{sample_id}.npy"
                audio_feat_path = feat_dir / "audio" / f"{sample_id}.npy"
                video_feat_path.parent.mkdir(parents=True, exist_ok=True)
                audio_feat_path.parent.mkdir(parents=True, exist_ok=True)

                if not video_feat_path.exists():
                    video_features = extract_video_features(str(clip_path), cfg)
                    np.save(video_feat_path, video_features)
                if not audio_feat_path.exists():
                    audio_features = load_audio_features(str(clip_path), cfg)
                    np.save(audio_feat_path, audio_features)

                rows.append(
                    {
                        "sample_id": sample_id,
                        "split": split,
                        "label": EMOTION_MAP[emotion],
                        "video_path": str(video_feat_path),
                        "audio_path": str(audio_feat_path),
                        "transcript": transcript,
                    }
                )
            except Exception as exc:
                skipped += 1
                print(f"Skipping {split} dia{dialogue_id}_utt{utterance_id}: {exc}")

        out_csv = manifest_dir / f"meld_{split}.csv"
        pd.DataFrame(rows).to_csv(out_csv, index=False)
        manifests.append((split, len(rows), out_csv))
        if skipped:
            print(f"Skipped {skipped} unreadable samples in {split}")

    for split, count, out_csv in manifests:
        print(f"Wrote {count} rows to {out_csv}")


if __name__ == "__main__":
    main()
