from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


SENTENCE_MAP = {
    "DFA": "Don't forget a jacket",
    "IEO": "It's eleven o'clock",
    "IOM": "I'm on my way to the meeting",
    "ITH": "I think I have a doctor's appointment",
    "ITS": "I think I've seen this before",
    "IWL": "I would like a new alarm clock",
    "IWW": "I wonder what this is about",
    "MTI": "Maybe tomorrow it will be cold",
    "TAI": "The airplane is almost full",
    "TIE": "That is exactly what happened",
    "TSI": "The surface is slick",
    "WSI": "We'll stop in a couple of minutes",
}

EMOTION_MAP = {
    "ANG": (0, "anger"),
    "DIS": (1, "disgust"),
    "FEA": (2, "fear"),
    "HAP": (3, "happy"),
    "NEU": (4, "neutral"),
    "SAD": (5, "sad"),
}

FILE_RE = re.compile(
    r"^(?P<actor_id>\d{4})_(?P<sentence_code>[A-Z]{3})_(?P<emotion_code>[A-Z]{3})_(?P<intensity_code>[A-Z]{2})(?:_(?P<clip_num>\d+))?(?:\.(?P<ext>[A-Za-z0-9]+))?$"
)


def infer_split(actor_id: str) -> str:
    """Deterministic speaker-based split.

    This is not an official CREMA-D split. It creates a stable train/val/test
    partition so the dataset can be used immediately in this project.
    """
    bucket = int(actor_id) % 10
    if bucket < 7:
        return "train"
    if bucket < 9:
        return "val"
    return "test"


def find_media_file(root: Path, relative_dir: str, stem: str) -> Path | None:
    candidates = [
        root / relative_dir / f"{stem}.wav",
        root / relative_dir / f"{stem}.mp3",
        root / relative_dir / f"{stem}.flv",
        root / relative_dir / f"{stem}.mp4",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in (root / relative_dir).rglob(f"{stem}.*"):
        if candidate.is_file():
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-generate CREMA-D labels.csv from the cloned repo metadata")
    parser.add_argument("--crema-repo", type=str, required=True, help="Path to the cloned CREMA-D repository")
    parser.add_argument("--output-csv", type=str, default="data/CREMA_D/labels.csv", help="Output labels CSV")
    parser.add_argument("--audio-dir", type=str, default="AudioWAV", help="Audio directory relative to the repo")
    parser.add_argument("--video-dir", type=str, default="VideoFlash", help="Video directory relative to the repo")
    parser.add_argument("--strict-media", action="store_true", help="Fail if any media file is missing")
    args = parser.parse_args()

    repo = Path(args.crema_repo)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    sentence_file = repo / "SentenceFilenames.csv"
    if not sentence_file.exists():
        raise FileNotFoundError(f"Missing SentenceFilenames.csv in {repo}")

    rows: list[dict[str, str | int]] = []
    skipped = 0

    with sentence_file.open(newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{sentence_file} has no header row")
        filename_key = next((key for key in reader.fieldnames if key.strip().lower() == "filename"), None)
        if filename_key is None:
            raise ValueError(f"{sentence_file} is missing a Filename column")

        for raw_row in reader:
            if not raw_row:
                continue
            file_name = str(raw_row.get(filename_key, "")).strip().strip('"')
            m = FILE_RE.match(file_name)
            if not m:
                skipped += 1
                continue

            actor_id = m.group("actor_id")
            sentence_code = m.group("sentence_code")
            emotion_code = m.group("emotion_code")
            intensity_code = m.group("intensity_code")
            ext = (m.group("ext") or "").lower()

            if sentence_code not in SENTENCE_MAP or emotion_code not in EMOTION_MAP:
                skipped += 1
                continue

            label, emotion = EMOTION_MAP[emotion_code]
            transcript = SENTENCE_MAP[sentence_code]
            split = infer_split(actor_id)
            sample_id = Path(file_name).stem

            audio_media = find_media_file(repo, args.audio_dir, Path(file_name).stem)
            video_media = find_media_file(repo, args.video_dir, Path(file_name).stem)

            if audio_media is None or video_media is None:
                if args.strict_media:
                    missing_parts = []
                    if audio_media is None:
                        missing_parts.append("audio")
                    if video_media is None:
                        missing_parts.append("video")
                    raise FileNotFoundError(f"Missing {' and '.join(missing_parts)} media for {file_name}")
                skipped += 1
                continue

            rows.append(
                {
                    "sample_id": sample_id,
                    "split": split,
                    "label": label,
                    "emotion": emotion,
                    "emotion_code": emotion_code,
                    "intensity_code": intensity_code,
                    "transcript": transcript,
                    "video_path": str(video_media.relative_to(repo)),
                    "audio_path": str(audio_media.relative_to(repo)),
                    "source_file": file_name,
                    "file_ext": ext,
                }
            )

    if not rows:
        raise ValueError(
            "No CREMA-D rows were generated. Check that the repo is cloned with Git LFS and that the media directories exist."
        )

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id",
                "split",
                "label",
                "emotion",
                "emotion_code",
                "intensity_code",
                "transcript",
                "video_path",
                "audio_path",
                "source_file",
                "file_ext",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_csv}")
    if skipped:
        print(f"Skipped {skipped} files that did not match the expected CREMA-D metadata or media layout.")


if __name__ == "__main__":
    main()
