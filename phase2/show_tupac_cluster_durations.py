from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
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


def duration(row: dict[str, str]) -> float:
    direct = seconds(row.get("turn_duration_seconds") or row.get("duration_seconds"))
    if direct > 0:
        return direct
    start = row.get("turn_start_time") or row.get("start_time")
    end = row.get("turn_end_time") or row.get("end_time")
    return max(0.0, seconds(end) - seconds(start))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report Tupac cluster row counts and durations without path-based joins."
    )
    parser.add_argument("--manifest-csv", required=True)
    parser.add_argument("--segments-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--source-group-id", default="")
    args = parser.parse_args()

    with Path(args.manifest_csv).open(newline="", encoding="utf-8-sig") as handle:
        manifest = list(csv.DictReader(handle))
    with Path(args.segments_csv).open(newline="", encoding="utf-8-sig") as handle:
        segments = list(csv.DictReader(handle))

    if args.source_group_id:
        manifest = [r for r in manifest if clean(r.get("youtube_id") or r.get("source_group_id")) == args.source_group_id]

    turn_counts = defaultdict(int)
    turn_seconds = defaultdict(float)
    roles = defaultdict(set)
    samples = defaultdict(list)
    for row in manifest:
        cluster = clean(row.get("speaker_cluster_id") or row.get("speaker_cluster_id", "")) or "UNKNOWN"
        turn_counts[cluster] += 1
        turn_seconds[cluster] += duration(row)
        role = clean(row.get("speaker_role") or row.get("role_label"))
        if role:
            roles[cluster].add(role)
        if len(samples[cluster]) < 10:
            samples[cluster].append(clean(row.get("utterance_id") or row.get("turn_id")))

    segment_counts = defaultdict(int)
    segment_seconds = defaultdict(float)
    for row in segments:
        cluster = clean(row.get("speaker_cluster_id")) or "UNKNOWN"
        segment_counts[cluster] += 1
        segment_seconds[cluster] += max(
            0.0,
            seconds(row.get("segment_end_seconds")) - seconds(row.get("segment_start_seconds")),
        )

    clusters = sorted(set(turn_counts) | set(segment_counts), key=lambda c: (-turn_counts[c], c))
    output_rows = []
    for cluster in clusters:
        output_rows.append({
            "source_group_id": args.source_group_id or clean(manifest[0].get("youtube_id")) if manifest else "",
            "speaker_cluster_id": cluster,
            "speaker_role": " | ".join(sorted(roles[cluster])) or "UNKNOWN",
            "total_clips": str(turn_counts[cluster]),
            "turn_rows": str(turn_counts[cluster]),
            "turn_seconds": f"{turn_seconds[cluster]:.3f}",
            "turn_minutes": f"{turn_seconds[cluster] / 60.0:.3f}",
            "diarization_segment_rows": str(segment_counts[cluster]),
            "diarization_segment_seconds": f"{segment_seconds[cluster]:.3f}",
            "diarization_segment_minutes": f"{segment_seconds[cluster] / 60.0:.3f}",
            "sample_utterance_ids": " | ".join(samples[cluster]),
        })

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        fields = list(output_rows[0]) if output_rows else [
            "source_group_id", "speaker_cluster_id", "turn_rows", "turn_seconds", "turn_minutes",
            "speaker_role", "total_clips",
            "diarization_segment_rows", "diarization_segment_seconds", "diarization_segment_minutes",
            "sample_utterance_ids",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "manifest_csv": args.manifest_csv,
        "segments_csv": args.segments_csv,
        "output_csv": args.output_csv,
        "rows_in_manifest": len(manifest),
        "rows_in_segments": len(segments),
        "clusters": len(output_rows),
        "turn_seconds_total": round(sum(turn_seconds.values()), 3),
        "segment_seconds_total": round(sum(segment_seconds.values()), 3),
        "note": "Turn and segment totals are calculated independently; no audio-path join is used.",
    }
    report = Path(args.output_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("source_group_id\tspeaker_cluster_id\tspeaker_role\ttotal_clips\tturn_seconds\tturn_minutes\tsegment_rows\tsegment_seconds\tsegment_minutes")
    for row in output_rows:
        print(
            f"{row['source_group_id']}\t{row['speaker_cluster_id']}\t{row['speaker_role']}\t"
            f"{row['total_clips']}\t{row['turn_seconds']}\t{row['turn_minutes']}\t{row['diarization_segment_rows']}\t"
            f"{row['diarization_segment_seconds']}\t{row['diarization_segment_minutes']}"
        )
    print(f"Wrote duration report to {output}")
    print(f"Wrote summary to {report}")


if __name__ == "__main__":
    main()
