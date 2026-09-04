from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def seconds(value: object) -> float:
    text = clean(value).replace(",", ".")
    if not text:
        return 0.0
    try:
        parts = text.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def timestamp(value: float) -> str:
    whole = int(max(0.0, value))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    millis = int(round((max(0.0, value) - whole) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def append_text(existing: str, incoming: str) -> str:
    left = clean(existing)
    right = clean(incoming)
    if not left:
        return right
    if not right or right == left:
        return left
    if right.startswith(left):
        return right
    if left.endswith(right):
        return left
    return f"{left} {right}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidate diarized subtitle cues into conversational Tupac turns."
    )
    parser.add_argument("--input-csv", required=True, help="Cue-preserved diarized manifest")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--include-youtube-id", default="")
    parser.add_argument("--max-gap-seconds", type=float, default=1.0)
    parser.add_argument("--min-duration-seconds", type=float, default=0.8)
    parser.add_argument("--max-duration-seconds", type=float, default=30.0)
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("Input CSV contains no rows")

    selected = [
        row for row in rows
        if not args.include_youtube_id or clean(row.get("youtube_id")) == args.include_youtube_id
    ]
    selected.sort(
        key=lambda row: (
            clean(row.get("youtube_id")),
            seconds(row.get("turn_start_time") or row.get("start_time")),
            clean(row.get("utterance_id")),
        )
    )

    groups: list[dict[str, str]] = []
    dropped_short = 0
    for row in selected:
        source = clean(row.get("youtube_id"))
        cluster = clean(row.get("speaker_cluster_id")) or "UNKNOWN"
        start = seconds(row.get("turn_start_time") or row.get("start_time"))
        end = seconds(row.get("turn_end_time") or row.get("end_time"))
        if end <= start:
            continue
        current = groups[-1] if groups else None
        gap = start - seconds(current["turn_end_time"]) if current else 999999.0
        current_duration = seconds(current["turn_end_time"]) - seconds(current["turn_start_time"]) if current else 0.0
        same_source = current and current["youtube_id"] == source
        same_cluster = current and current["speaker_cluster_id"] == cluster
        within_gap = current and gap <= args.max_gap_seconds
        within_duration = current and end - seconds(current["turn_start_time"]) <= args.max_duration_seconds
        if same_source and same_cluster and within_gap and within_duration:
            current["turn_end_time"] = timestamp(end)
            current["turn_duration_seconds"] = f"{end - seconds(current['turn_start_time']):.3f}"
            current["turn_text"] = append_text(current["turn_text"], row.get("turn_text") or row.get("utterance_text"))
            current["utterance_text"] = current["turn_text"]
            current["turn_piece_count"] = str(int(current["turn_piece_count"]) + 1)
            current["turn_piece_ids"] += " | " + clean(row.get("utterance_id") or row.get("turn_id"))
            current["turn_source_utterance_count"] = current["turn_piece_count"]
        else:
            if current and current_duration < args.min_duration_seconds:
                dropped_short += 1
            text = clean(row.get("turn_text") or row.get("utterance_text"))
            groups.append({
                "youtube_id": source,
                "source_url": clean(row.get("source_url")),
                "title": clean(row.get("title")),
                "category": clean(row.get("category")),
                "priority": clean(row.get("priority")),
                "subtitle_path": clean(row.get("subtitle_path")),
                "video_path": clean(row.get("video_path")),
                "audio_path": clean(row.get("audio_path")),
                "split_group_id": source,
                "split_strategy": "source_cluster_consolidation",
                "split": clean(row.get("split")),
                "emotion_label": clean(row.get("emotion_label")),
                "emotion_label_source": clean(row.get("emotion_label_source")),
                "emotion_label_confidence": clean(row.get("emotion_label_confidence")),
                "review_flag": clean(row.get("review_flag")),
                "review_reason": clean(row.get("review_reason")),
                "usable_for_phase2": clean(row.get("usable_for_phase2")),
                "speaker_cluster_id": cluster,
                "speaker_cluster_source": clean(row.get("speaker_cluster_source")),
                "turn_start_time": timestamp(start),
                "turn_end_time": timestamp(end),
                "turn_duration_seconds": f"{end - start:.3f}",
                "duration_seconds": f"{end - start:.3f}",
                "turn_text": text,
                "utterance_text": text,
                "turn_boundary_type": "speaker_cluster_gap_or_duration",
                "turn_confidence": "",
                "turn_marker_count": "0",
                "turn_piece_count": "1",
                "turn_piece_ids": clean(row.get("utterance_id") or row.get("turn_id")),
                "turn_source_utterance_ids": clean(row.get("utterance_id") or row.get("turn_id")),
                "turn_source_utterance_count": "1",
            })

    groups = [
        group for group in groups
        if seconds(group["turn_end_time"]) - seconds(group["turn_start_time"]) >= args.min_duration_seconds
    ]
    output_rows = []
    for index, group in enumerate(groups, 1):
        group["turn_id"] = f"{group['youtube_id']}_turn{index:05d}"
        group["utterance_id"] = group["turn_id"]
        output_rows.append(group)

    fields = list(output_rows[0]) if output_rows else [
        "turn_id", "utterance_id", "youtube_id", "source_url", "title", "category", "priority",
        "subtitle_path", "video_path", "audio_path", "split_group_id", "split_strategy", "split",
        "emotion_label", "emotion_label_source", "emotion_label_confidence", "review_flag",
        "review_reason", "usable_for_phase2", "speaker_cluster_id", "speaker_cluster_source",
        "turn_start_time", "turn_end_time", "turn_duration_seconds", "duration_seconds", "turn_text",
        "utterance_text", "turn_boundary_type", "turn_confidence", "turn_marker_count",
        "turn_piece_count", "turn_piece_ids", "turn_source_utterance_ids", "turn_source_utterance_count",
    ]
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "input_csv": str(args.input_csv),
        "output_csv": str(args.output_csv),
        "rows_input": len(rows),
        "rows_selected": len(selected),
        "conversational_turns_written": len(output_rows),
        "rows_dropped_below_min_duration": dropped_short,
        "unique_youtube_ids": sorted({row["youtube_id"] for row in output_rows}),
        "cluster_counts": {
            cluster: sum(1 for row in output_rows if row["speaker_cluster_id"] == cluster)
            for cluster in sorted({row["speaker_cluster_id"] for row in output_rows})
        },
        "parameters": {
            "max_gap_seconds": args.max_gap_seconds,
            "min_duration_seconds": args.min_duration_seconds,
            "max_duration_seconds": args.max_duration_seconds,
        },
        "policy": "merge adjacent cues only within the same source and diarization cluster",
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

