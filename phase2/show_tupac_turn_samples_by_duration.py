from __future__ import annotations

import argparse
import csv
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


def turn_duration(row: dict[str, str]) -> float:
    direct = seconds(row.get("turn_duration_seconds") or row.get("duration_seconds"))
    if direct > 0:
        return direct
    return max(
        0.0,
        seconds(row.get("turn_end_time") or row.get("end_time"))
        - seconds(row.get("turn_start_time") or row.get("start_time")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print longer Tupac conversational-turn samples by speaker cluster."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--source-group-id", default="")
    parser.add_argument("--min-duration-seconds", type=float, default=2.5)
    parser.add_argument("--samples-per-cluster", type=int, default=5)
    parser.add_argument("--speaker-cluster", default="")
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("Input CSV contains no rows")
    if args.samples_per_cluster < 1:
        raise SystemExit("--samples-per-cluster must be at least 1")

    selected = []
    for row in rows:
        source = clean(row.get("youtube_id") or row.get("source_group_id"))
        cluster = clean(row.get("speaker_cluster_id")) or "UNKNOWN"
        if args.source_group_id and source != args.source_group_id:
            continue
        if args.speaker_cluster and cluster != args.speaker_cluster:
            continue
        row["_duration"] = turn_duration(row)
        if row["_duration"] >= args.min_duration_seconds:
            selected.append(row)

    grouped = defaultdict(list)
    for row in selected:
        grouped[clean(row.get("speaker_cluster_id")) or "UNKNOWN"].append(row)
    for cluster in grouped:
        grouped[cluster].sort(key=lambda row: (-row["_duration"], clean(row.get("turn_id"))))

    print(
        f"Input rows: {len(rows)} | Matching rows: {len(selected)} | "
        f"Minimum duration: {args.min_duration_seconds:.3f}s | "
        f"Clusters: {len(grouped)}"
    )
    for index, cluster in enumerate(sorted(grouped), 1):
        rows_for_cluster = grouped[cluster]
        print(f"\n=== Cluster {index}: {cluster} ({len(rows_for_cluster)} matching rows) ===")
        for sample_index, row in enumerate(rows_for_cluster[: args.samples_per_cluster], 1):
            print(f"\n--- Sample {sample_index} ---")
            print(f"Utterance ID: {clean(row.get('utterance_id') or row.get('turn_id'))}")
            print(f"Duration: {row['_duration']:.3f} sec")
            print(
                f"Time: {clean(row.get('turn_start_time') or row.get('start_time'))} -> "
                f"{clean(row.get('turn_end_time') or row.get('end_time'))}"
            )
            print(f"Role: {clean(row.get('speaker_role') or row.get('role_label')) or 'UNASSIGNED'}")
            print(f"Audio clip: {clean(row.get('clip_audio_path') or row.get('audio_path'))}")
            print(f"Video clip: {clean(row.get('clip_video_path') or row.get('video_path'))}")
            print(f"Transcript: {clean(row.get('turn_text') or row.get('utterance_text'))}")


if __name__ == "__main__":
    main()

