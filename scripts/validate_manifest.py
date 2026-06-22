from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"sample_id", "split", "label", "video_path", "audio_path", "transcript"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a multimodal manifest CSV")
    parser.add_argument("--manifest", type=str, required=True, help="Path to the manifest CSV")
    parser.add_argument("--max-samples", type=int, default=5, help="Number of examples to print")
    parser.add_argument("--strict-exists", action="store_true", help="Fail if media paths do not exist")
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest}")

    df = pd.read_csv(manifest)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Manifest is missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError("Manifest contains no rows")

    print(f"Manifest: {manifest}")
    print(f"Rows: {len(df)}")
    print(f"Splits: {df['split'].value_counts().to_dict()}")
    print(f"Label counts: {df['label'].value_counts().to_dict()}")

    if args.strict_exists:
        missing_audio = []
        missing_video = []
        for _, row in df.iterrows():
            audio_path = Path(str(row["audio_path"]))
            video_path = Path(str(row["video_path"]))
            if not audio_path.exists():
                missing_audio.append(str(audio_path))
            if not video_path.exists():
                missing_video.append(str(video_path))
        if missing_audio or missing_video:
            print(f"Missing audio files: {len(missing_audio)}")
            print(f"Missing video files: {len(missing_video)}")
            raise FileNotFoundError("One or more media files referenced by the manifest do not exist")

    print("Sample rows:")
    for _, row in df.head(args.max_samples).iterrows():
        print(
            {
                "sample_id": row["sample_id"],
                "split": row["split"],
                "label": row["label"],
                "audio_path": row["audio_path"],
                "video_path": row["video_path"],
            }
        )


if __name__ == "__main__":
    main()
