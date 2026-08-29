"""Read-only EDA for the accepted Clancy witness-speaking pool."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def text(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(text(row, key))
    except ValueError:
        return 0.0


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = (len(values) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    return dict(Counter(text(row, key) or "BLANK" for row in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-csv",
        default="data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_usable.csv",
    )
    parser.add_argument(
        "--summary-json",
        default="reports/phase2/clancy_witness_speaking_usable_eda.json",
    )
    parser.add_argument(
        "--source-csv",
        default="reports/phase2/clancy_witness_speaking_usable_by_source.csv",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    with input_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"No rows found in {input_path}")

    durations = sorted(number(row, "clip_duration_seconds") for row in rows)
    sources: dict[str, dict[str, object]] = defaultdict(
        lambda: {"rows": 0, "seconds": 0.0, "witness_clusters": set(), "splits": Counter()}
    )
    for row in rows:
        source = text(row, "youtube_id") or "BLANK"
        item = sources[source]
        item["rows"] = int(item["rows"]) + 1
        item["seconds"] = float(item["seconds"]) + number(row, "clip_duration_seconds")
        cluster = text(row, "speaker_cluster_id")
        if cluster:
            item["witness_clusters"].add(cluster)
        item["splits"][text(row, "split") or "BLANK"] += 1

    source_rows = []
    for source, item in sorted(sources.items(), key=lambda pair: (-int(pair[1]["rows"]), pair[0])):
        source_rows.append(
            {
                "youtube_id": source,
                "rows": int(item["rows"]),
                "clip_minutes": round(float(item["seconds"]) / 60.0, 3),
                "clip_hours": round(float(item["seconds"]) / 3600.0, 4),
                "unique_speaker_clusters": len(item["witness_clusters"]),
                "split_counts": json.dumps(dict(item["splits"]), sort_keys=True),
            }
        )

    def existing_path_count(key: str) -> int:
        return sum(bool(text(row, key)) and Path(text(row, key)).exists() for row in rows)

    def duplicate_count(key: str) -> int:
        values = [text(row, key) for row in rows if text(row, key)]
        return len(values) - len(set(values))

    visual_statuses = counts(rows, "visual_verification_status")
    human_verified = visual_statuses.get("HUMAN_VERIFIED", 0)
    summary = {
        "input_csv": str(input_path),
        "rows": len(rows),
        "unique_turn_ids": len({text(row, "turn_id") for row in rows}),
        "unique_utterance_ids": len({text(row, "utterance_id") for row in rows}),
        "unique_source_videos": len(sources),
        "unique_speaker_clusters": len({text(row, "speaker_cluster_id") for row in rows if text(row, "speaker_cluster_id")}),
        "duration": {
            "total_seconds": round(sum(durations), 3),
            "total_minutes": round(sum(durations) / 60.0, 3),
            "total_hours": round(sum(durations) / 3600.0, 4),
            "min_seconds": round(durations[0], 3),
            "p25_seconds": round(percentile(durations, 0.25), 3),
            "median_seconds": round(statistics.median(durations), 3),
            "mean_seconds": round(statistics.mean(durations), 3),
            "p75_seconds": round(percentile(durations, 0.75), 3),
            "p95_seconds": round(percentile(durations, 0.95), 3),
            "max_seconds": round(durations[-1], 3),
            "band_0_8_to_under_20_rows": sum(0.8 <= value < 20.0 for value in durations),
            "band_0_8_to_under_20_minutes": round(sum(value for value in durations if 0.8 <= value < 20.0) / 60.0, 3),
            "band_20_to_30_rows": sum(20.0 <= value <= 30.0 for value in durations),
            "band_20_to_30_minutes": round(sum(value for value in durations if 20.0 <= value <= 30.0) / 60.0, 3),
            "below_0_8_rows": sum(value < 0.8 for value in durations),
            "above_30_rows": sum(value > 30.0 for value in durations),
        },
        "categorical_counts": {
            key: counts(rows, key)
            for key in (
                "youtube_id",
                "speaker_role",
                "witness_speaking_status",
                "visual_target_role",
                "visual_speaker_match",
                "speaker_visible_during_speech",
                "visual_verification_confidence",
                "visual_verification_status",
                "split",
                "clip_status",
                "source_offset_status",
                "speaker_role_confidence",
            )
        },
        "text_completeness": {
            "blank_turn_text": sum(not text(row, "turn_text") for row in rows),
            "blank_utterance_text": sum(not text(row, "utterance_text") for row in rows),
        },
        "media_integrity": {
            "video_files_existing": existing_path_count("clip_video_path"),
            "audio_files_existing": existing_path_count("clip_audio_path"),
            "video_paths_missing": sum(not text(row, "clip_video_path") for row in rows),
            "audio_paths_missing": sum(not text(row, "clip_audio_path") for row in rows),
            "duplicate_turn_ids": duplicate_count("turn_id"),
            "duplicate_utterance_ids": duplicate_count("utterance_id"),
            "duplicate_video_clip_paths": duplicate_count("clip_video_path"),
            "duplicate_audio_clip_paths": duplicate_count("clip_audio_path"),
        },
        "interpretation": [
            (
                "All rows are marked HUMAN_VERIFIED for visual presence based on the supplied review decision."
                if human_verified == len(rows)
                else "The pool contains a mixture of human-verified and non-human-verified visual statuses."
            ),
            "Visual verification supports witness visibility claims; it does not validate emotion or credibility labels.",
            "The duration total is summed clip duration and should not be treated as independent raw-video hours.",
        ],
        "source_csv": str(Path(args.source_csv)),
    }

    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    source_path = Path(args.source_csv)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    with source_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(source_rows[0]))
        writer.writeheader()
        writer.writerows(source_rows)
    print(json.dumps(summary, indent=2))
    print(f"Wrote source EDA to {source_path}")


if __name__ == "__main__":
    main()
