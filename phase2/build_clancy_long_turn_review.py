from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a review manifest for unusually long Clancy turn clips")
    parser.add_argument("--input-csv", default="data/processed/phase2/clancy/clancy_turn_manifest_clipped.csv")
    parser.add_argument("--output-csv", default="data/processed/phase2/clancy/clancy_long_turn_review.csv")
    parser.add_argument("--threshold-seconds", type=float, default=30.0)
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output_csv)
    with input_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    selected = []
    for row in rows:
        try:
            duration = float(row.get("clip_duration_seconds") or 0.0)
        except ValueError:
            duration = 0.0
        if duration <= args.threshold_seconds:
            continue
        selected.append(
            {
                "turn_id": row.get("turn_id", ""),
                "youtube_id": row.get("youtube_id", ""),
                "source_url": row.get("source_url", ""),
                "title": row.get("title", ""),
                "raw_video_path": row.get("source_video_path", ""),
                "raw_subtitle_path": row.get("subtitle_path", ""),
                "clip_video_path": row.get("clip_video_path", ""),
                "clip_audio_path": row.get("clip_audio_path", ""),
                "turn_start_time": row.get("turn_start_time", ""),
                "turn_end_time": row.get("turn_end_time", ""),
                "clip_duration_seconds": row.get("clip_duration_seconds", ""),
                "turn_source_utterance_count": row.get("turn_source_utterance_count", ""),
                "review_status": "REVIEW_REQUIRED",
                "review_reason": "Turn exceeds MELD-style preferred maximum duration; inspect for over-consolidation, pauses, or non-testimony content.",
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(selected[0].keys()) if selected else [
        "turn_id", "youtube_id", "source_url", "title", "raw_video_path", "raw_subtitle_path",
        "clip_video_path", "clip_audio_path", "turn_start_time", "turn_end_time",
        "clip_duration_seconds", "turn_source_utterance_count", "review_status", "review_reason",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    print(f"Wrote {len(selected)} long-turn review rows to {output_path}")


if __name__ == "__main__":
    main()
