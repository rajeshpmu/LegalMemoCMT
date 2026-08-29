from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Show all Clancy source-local speaker clusters and row counts")
    parser.add_argument("--manifest-csv", required=True, help="Diarization-enriched turn manifest")
    parser.add_argument("--segments-csv", default="", help="Optional source-level diarization segment CSV")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()

    manifest = read_csv(Path(args.manifest_csv))
    if not manifest:
        raise SystemExit("Manifest contains no rows")

    segment_counts: dict[tuple[str, str], int] = defaultdict(int)
    segment_seconds: dict[tuple[str, str], float] = defaultdict(float)
    if args.segments_csv:
        segment_path = Path(args.segments_csv)
        if segment_path.exists():
            for row in read_csv(segment_path):
                key = (row.get("source_audio_path", ""), row.get("speaker_cluster_id", ""))
                segment_counts[key] += 1
                segment_seconds[key] += max(
                    0.0,
                    number(row.get("segment_end_seconds", ""))
                    - number(row.get("segment_start_seconds", "")),
                )

    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in manifest:
        key = (row.get("youtube_id", ""), row.get("speaker_cluster_id", "UNKNOWN"))
        groups[key].append(row)

    output_rows: list[dict[str, str]] = []
    for (source, cluster), rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        source_audio = rows[0].get("source_audio_path", "")
        key = (source_audio, cluster)
        output_rows.append({
            "source_group_id": source,
            "source_audio_path": source_audio,
            "speaker_cluster_id": cluster,
            "manifest_turn_row_count": str(len(rows)),
            "diarization_segment_count": str(segment_counts.get(key, 0)),
            "diarization_segment_seconds": f"{segment_seconds.get(key, 0.0):.3f}",
            "sample_utterance_ids": " | ".join(row.get("utterance_id", "") for row in rows[: args.samples]),
            "sample_time_ranges": " | ".join(
                f"{row.get('start_time', row.get('turn_start_time', ''))} -> "
                f"{row.get('end_time', row.get('turn_end_time', ''))}"
                for row in rows[: args.samples]
            ),
            "sample_clip_video_paths": " | ".join(
                row.get("clip_video_path", row.get("video_path", ""))
                for row in rows[: args.samples]
            ),
            "sample_clip_audio_paths": " | ".join(
                row.get("clip_audio_path", row.get("audio_path", ""))
                for row in rows[: args.samples]
            ),
            "sample_text": " || ".join(row.get("utterance_text", "")[:240] for row in rows[: args.samples]),
            "role_label": rows[0].get("speaker_role", "UNKNOWN"),
            "role_confidence": rows[0].get("speaker_role_confidence", "LOW"),
            "witness_speaking_status": rows[0].get("witness_speaking_status", "UNKNOWN"),
        })

    fields = list(output_rows[0].keys()) if output_rows else []
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "manifest_csv": args.manifest_csv,
        "segments_csv": args.segments_csv,
        "output_csv": args.output_csv,
        "cluster_rows": len(output_rows),
        "source_groups": len({row["source_group_id"] for row in output_rows}),
        "manifest_rows": len(manifest),
        "clusters_by_source": {
            source: sum(1 for row in output_rows if row["source_group_id"] == source)
            for source in sorted({row["source_group_id"] for row in output_rows})
        },
    }
    json_path = Path(args.output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"source_groups={summary['source_groups']} clusters={summary['cluster_rows']} manifest_rows={summary['manifest_rows']}")
    print("source_group_id\tspeaker_cluster_id\tturn_rows\tsegment_rows\tsegment_seconds\trole\tstatus")
    for row in output_rows:
        print(
            f"{row['source_group_id']}\t{row['speaker_cluster_id']}\t"
            f"{row['manifest_turn_row_count']}\t{row['diarization_segment_count']}\t"
            f"{row['diarization_segment_seconds']}\t{row['role_label']}\t"
            f"{row['witness_speaking_status']}"
        )
    print(f"Wrote cluster inventory to {output_path}")
    print(f"Wrote summary to {json_path}")


if __name__ == "__main__":
    main()
