from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def number(value: object) -> float:
    try:
        return float(clean(value))
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create one Tupac turn row per source subtitle cue without consolidating cues."
    )
    parser.add_argument("--input-csv", required=True, help="Source-specific utterance manifest")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--include-youtube-id", default="", help="Optional exact source filter")
    parser.add_argument("--min-duration", type=float, default=0.0)
    parser.add_argument("--max-duration", type=float, default=0.0)
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output_csv)
    summary_path = Path(args.summary_json)
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise SystemExit("Input utterance manifest contains no rows")

    selected = []
    rejected = 0
    for row in rows:
        youtube_id = clean(row.get("youtube_id"))
        if args.include_youtube_id and youtube_id != args.include_youtube_id:
            continue
        duration = number(row.get("duration_seconds"))
        if args.min_duration and duration < args.min_duration:
            rejected += 1
            continue
        if args.max_duration and duration > args.max_duration:
            rejected += 1
            continue
        if not clean(row.get("utterance_text")):
            rejected += 1
            continue
        selected.append(row)

    selected.sort(key=lambda row: (clean(row.get("youtube_id")), number(row.get("start_time")), clean(row.get("utterance_id"))))
    output_rows = []
    for index, row in enumerate(selected, 1):
        start = clean(row.get("start_time"))
        end = clean(row.get("end_time"))
        duration = number(row.get("duration_seconds"))
        output_rows.append({
            "turn_id": f"{clean(row.get('youtube_id'))}_turn{index:05d}",
            "utterance_id": clean(row.get("utterance_id")),
            "youtube_id": clean(row.get("youtube_id")),
            "source_url": clean(row.get("source_url")),
            "title": clean(row.get("title")),
            "category": clean(row.get("category")),
            "priority": clean(row.get("priority")),
            "subtitle_path": clean(row.get("subtitle_path")),
            "video_path": clean(row.get("video_path")),
            "audio_path": clean(row.get("audio_path")),
            "split_group_id": clean(row.get("youtube_id")),
            "split_strategy": "source_group",
            "split": clean(row.get("split")),
            "emotion_label": clean(row.get("emotion_label")),
            "emotion_label_source": clean(row.get("emotion_label_source")),
            "emotion_label_confidence": clean(row.get("emotion_label_confidence")),
            "review_flag": clean(row.get("review_flag")),
            "review_reason": clean(row.get("review_reason")),
            "usable_for_phase2": clean(row.get("usable_for_phase2")),
            "turn_text": clean(row.get("utterance_text")),
            "utterance_text": clean(row.get("utterance_text")),
            "turn_start_time": start,
            "turn_end_time": end,
            "turn_duration_seconds": f"{duration:.3f}",
            "duration_seconds": f"{duration:.3f}",
            "turn_boundary_type": "subtitle_cue_preserved",
            "turn_confidence": "",
            "turn_marker_count": "0",
            "turn_piece_count": "1",
            "turn_piece_ids": clean(row.get("utterance_id")),
            "turn_source_utterance_ids": clean(row.get("utterance_id")),
            "turn_source_utterance_count": "1",
        })

    fields = list(output_rows[0]) if output_rows else [
        "turn_id", "utterance_id", "youtube_id", "source_url", "title", "category", "priority",
        "subtitle_path", "video_path", "audio_path", "split_group_id", "split_strategy", "split",
        "emotion_label", "emotion_label_source", "emotion_label_confidence", "review_flag",
        "review_reason", "usable_for_phase2", "turn_text", "utterance_text", "turn_start_time",
        "turn_end_time", "turn_duration_seconds", "duration_seconds", "turn_boundary_type",
        "turn_confidence", "turn_marker_count", "turn_piece_count", "turn_piece_ids",
        "turn_source_utterance_ids", "turn_source_utterance_count",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "summary_json": str(summary_path),
        "rows_input": len(rows),
        "rows_selected": len(selected),
        "rows_rejected": rejected,
        "unique_youtube_ids": sorted({row["youtube_id"] for row in output_rows if row["youtube_id"]}),
        "turn_boundary_policy": "one output turn per non-empty source subtitle cue; no cue consolidation",
        "status": "PASS" if output_rows else "FAIL",
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

