from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"sample_id", "split", "label", "audio_path", "video_path", "transcript"}


def _path_exists(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        return Path(text).expanduser().exists()
    except OSError:
        return False


def _looks_like_reference(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return text.endswith((".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".flv", ".npy"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check whether a manifest's referenced files already exist on disk"
    )
    parser.add_argument("--manifest", type=str, required=True, help="Path to the manifest CSV")
    parser.add_argument(
        "--assume-text-inline",
        action="store_true",
        help="Treat non-empty transcript values as inline text instead of file paths",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit non-zero if any required path is missing",
    )
    parser.add_argument("--max-samples", type=int, default=5, help="Number of sample rows to print")
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest}")

    df = pd.read_csv(manifest)
    missing_cols = REQUIRED_COLUMNS - set(df.columns)
    if missing_cols:
        raise ValueError(f"Manifest is missing required columns: {sorted(missing_cols)}")
    if df.empty:
        raise ValueError("Manifest contains no rows")

    total = len(df)
    audio_ok = 0
    video_ok = 0
    transcript_ok = 0
    missing_audio: list[str] = []
    missing_video: list[str] = []
    missing_transcript: list[str] = []
    raw_like_media = 0

    for _, row in df.iterrows():
        sample_id = str(row["sample_id"])
        audio_path = row["audio_path"]
        video_path = row["video_path"]
        transcript = row["transcript"]

        if _path_exists(audio_path):
            audio_ok += 1
        else:
            missing_audio.append(str(audio_path))
        if _path_exists(video_path):
            video_ok += 1
        else:
            missing_video.append(str(video_path))

        if args.assume_text_inline:
            if str(transcript).strip():
                transcript_ok += 1
            else:
                missing_transcript.append(sample_id)
        else:
            # If transcript looks like a path and exists, or if it is inline text,
            # count it as available. Inline transcripts are the normal MELD case.
            if (str(transcript).strip() and not _looks_like_reference(transcript)) or _path_exists(transcript):
                transcript_ok += 1
            else:
                missing_transcript.append(sample_id)

        if _looks_like_reference(audio_path) or _looks_like_reference(video_path):
            raw_like_media += 1

    all_present = not missing_audio and not missing_video and not missing_transcript
    raw_needed = not all_present or raw_like_media > 0

    print(f"Manifest: {manifest}")
    print(f"Rows: {total}")
    print(f"Audio present: {audio_ok}/{total}")
    print(f"Video present: {video_ok}/{total}")
    print(f"Transcript present: {transcript_ok}/{total}")
    print(f"Rows with raw-media-like references: {raw_like_media}")
    print(f"All required files present: {all_present}")
    print(f"Raw data still needed: {raw_needed}")

    if missing_audio:
        print(f"Missing audio examples: {missing_audio[:args.max_samples]}")
    if missing_video:
        print(f"Missing video examples: {missing_video[:args.max_samples]}")
    if missing_transcript:
        print(f"Missing transcript examples: {missing_transcript[:args.max_samples]}")

    print("Sample rows:")
    for _, row in df.head(args.max_samples).iterrows():
        print(
            {
                "sample_id": row["sample_id"],
                "audio_path": row["audio_path"],
                "video_path": row["video_path"],
                "transcript": row["transcript"],
            }
        )

    if args.fail_on_missing and not all_present:
        raise FileNotFoundError("One or more manifest references are missing")


if __name__ == "__main__":
    main()
