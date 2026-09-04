from __future__ import annotations

import argparse
import csv
from pathlib import Path


def split_samples(value: str) -> list[str]:
    separator = " || " if " || " in (value or "") else " | "
    return [item.strip() for item in (value or "").split(separator) if item.strip()]


def print_cluster(row: dict[str, str], index: int, limit: int) -> None:
    cluster = row.get("speaker_cluster_id", "")
    role = row.get("role_label", "") or "UNASSIGNED"
    print(f"\n--- Cluster {index}: {cluster} | current role: {role} | confidence: {row.get('role_confidence', '')} ---")
    print(f"Source: {row.get('source_group_id', '')}")
    print(f"Rows: {row.get('cluster_row_count', '')}")
    print(f"Witness in segment: {row.get('witness_in_segment', '')}")
    print(f"Witness speaking status: {row.get('witness_speaking_status', '')}")
    ids = split_samples(row.get("sample_utterance_ids", ""))
    audios = split_samples(row.get("sample_audio_paths", ""))
    videos = split_samples(row.get("sample_video_paths", ""))
    texts = split_samples(row.get("sample_text", ""))
    count = min(limit, max(len(ids), len(audios), len(videos), len(texts)))
    for sample_index in range(count):
        print(f"\n  Sample {sample_index + 1}")
        if sample_index < len(ids):
            print(f"  Utterance ID: {ids[sample_index]}")
        if sample_index < len(audios):
            print(f"  Audio: {audios[sample_index]}")
        if sample_index < len(videos):
            print(f"  Video: {videos[sample_index]}")
        if sample_index < len(texts):
            print(f"  Transcript: {texts[sample_index]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pretty-print role-review cluster samples for manual speaker-role assignment."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--samples-per-cluster", type=int, default=3)
    parser.add_argument("--source-group-id", default="")
    parser.add_argument("--speaker-cluster", default="")
    parser.add_argument("--role-label", default="")
    args = parser.parse_args()

    if args.samples_per_cluster < 1:
        raise SystemExit("--samples-per-cluster must be at least 1")

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise SystemExit("Input CSV contains no rows")

    selected = []
    for row in rows:
        if args.source_group_id and row.get("source_group_id", "") != args.source_group_id:
            continue
        if args.speaker_cluster and row.get("speaker_cluster_id", "") != args.speaker_cluster:
            continue
        if args.role_label and row.get("role_label", "") != args.role_label:
            continue
        selected.append(row)

    if not selected:
        raise SystemExit("No rows matched the requested filters")

    selected.sort(key=lambda row: (row.get("source_group_id", ""), row.get("speaker_cluster_id", "")))
    print(f"Input rows: {len(rows)} | Selected clusters: {len(selected)}")
    for index, row in enumerate(selected, 1):
        print_cluster(row, index, args.samples_per_cluster)


if __name__ == "__main__":
    main()
