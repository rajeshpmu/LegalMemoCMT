from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistently reject Clancy duration-outlier rows")
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--rejection-csv", required=True)
    parser.add_argument("--min-seconds", type=float, default=0.8)
    parser.add_argument("--max-seconds", type=float, default=30.0)
    args = parser.parse_args()

    review_path = Path(args.review_csv)
    rejection_path = Path(args.rejection_csv)
    review_rows = read(review_path)
    existing = read(rejection_path) if rejection_path.exists() else []
    existing_ids = {row.get("turn_id") or row.get("utterance_id") for row in existing}

    outliers: list[dict[str, str]] = []
    for row in review_rows:
        try:
            duration = float(row.get("clip_duration_seconds") or row.get("turn_duration_seconds") or 0)
        except ValueError:
            continue
        if duration < args.min_seconds or duration > args.max_seconds:
            row_id = row.get("turn_id") or row.get("utterance_id")
            if not row_id or row_id in existing_ids:
                continue
            outliers.append({
                "turn_id": row_id,
                "youtube_id": row.get("youtube_id", ""),
                "source_url": row.get("source_url", ""),
                "title": row.get("title", ""),
                "raw_video_path": row.get("raw_video_path") or row.get("source_video_path", ""),
                "raw_subtitle_path": row.get("raw_subtitle_path") or row.get("subtitle_path", ""),
                "clip_video_path": row.get("clip_video_path", ""),
                "clip_audio_path": row.get("clip_audio_path", ""),
                "turn_start_time": row.get("turn_start_time") or row.get("start_time", ""),
                "turn_end_time": row.get("turn_end_time") or row.get("end_time", ""),
                "clip_duration_seconds": row.get("clip_duration_seconds") or row.get("turn_duration_seconds", ""),
                "rejection_status": "REJECTED",
                "rejection_reason": f"Duration outlier: outside {args.min_seconds:g}-{args.max_seconds:g} second MELD-style range",
            })
            existing_ids.add(row_id)

    fieldnames = [
        "turn_id", "youtube_id", "source_url", "title", "raw_video_path", "raw_subtitle_path",
        "clip_video_path", "clip_audio_path", "turn_start_time", "turn_end_time",
        "clip_duration_seconds", "rejection_status", "rejection_reason",
    ]
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    with rejection_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)
        writer.writerows(outliers)
    print(f"Review outliers found: {len([row for row in review_rows if _is_outlier(row, args.min_seconds, args.max_seconds)])}")
    print(f"New rejection rows appended: {len(outliers)}")
    print(f"Total persistent rejection rows: {len(existing) + len(outliers)}")
    print(f"Wrote {rejection_path}")


def _is_outlier(row: dict[str, str], minimum: float, maximum: float) -> bool:
    try:
        duration = float(row.get("clip_duration_seconds") or row.get("turn_duration_seconds") or 0)
    except ValueError:
        return False
    return duration < minimum or duration > maximum


if __name__ == "__main__":
    main()
