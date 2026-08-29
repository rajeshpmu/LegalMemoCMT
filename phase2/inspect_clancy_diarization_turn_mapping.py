from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def turn_times(row: dict[str, str]) -> tuple[float, float]:
    if row.get("turn_start_time") and row.get("turn_end_time"):
        return seconds(row["turn_start_time"]), seconds(row["turn_end_time"])
    offset = float(row.get("source_offset_seconds") or 0)
    return (
        max(0.0, seconds(row.get("start_time", "00:00:00.000")) - offset),
        max(0.0, seconds(row.get("end_time", "00:00:00.000")) - offset),
    )


def overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Map Clancy diarization segments back to overlapping turn clips")
    parser.add_argument("--segments-csv", required=True)
    parser.add_argument("--turns-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()

    segments = read_csv(Path(args.segments_csv))
    turns = read_csv(Path(args.turns_csv))
    turns_by_source: dict[str, list[dict[str, object]]] = defaultdict(list)
    for turn in turns:
        start, end = turn_times(turn)
        turns_by_source[turn.get("source_audio_path", "")].append({"row": turn, "start": start, "end": end})
    for source in turns_by_source:
        turns_by_source[source].sort(key=lambda item: float(item["start"]))

    output_rows: list[dict[str, str]] = []
    mapped_segments = 0
    multi_turn_segments = 0
    sources_with_segments = set()
    for segment in segments:
        source = segment.get("source_audio_path", "")
        sources_with_segments.add(source)
        seg_start = float(segment.get("segment_start_seconds", 0))
        seg_end = float(segment.get("segment_end_seconds", 0))
        matches: list[tuple[float, dict[str, object]]] = []
        for item in turns_by_source.get(source, []):
            if float(item["start"]) >= seg_end:
                break
            amount = overlap(seg_start, seg_end, float(item["start"]), float(item["end"]))
            if amount > 0:
                matches.append((amount, item))
        matches.sort(key=lambda item: item[0], reverse=True)
        if matches:
            mapped_segments += 1
        if len(matches) > 1:
            multi_turn_segments += 1
        best = matches[0][1]["row"] if matches else {}
        best_overlap = matches[0][0] if matches else 0.0
        output_rows.append({
            "source_audio_path": source,
            "speaker_cluster_id": segment.get("speaker_cluster_id", ""),
            "segment_start_seconds": segment.get("segment_start_seconds", ""),
            "segment_end_seconds": segment.get("segment_end_seconds", ""),
            "diarization_model": segment.get("diarization_model", ""),
            "mapping_status": "mapped" if matches else "no_overlapping_turn",
            "overlapping_utterance_ids": " | ".join(str(item["row"].get("utterance_id", "")) for _, item in matches),
            "best_utterance_id": str(best.get("utterance_id", "")),
            "best_clip_video_path": str(best.get("clip_video_path", "")),
            "best_clip_audio_path": str(best.get("clip_audio_path", "")),
            "best_overlap_seconds": f"{best_overlap:.3f}",
            "overlapping_turn_count": str(len(matches)),
        })

    fields = list(output_rows[0].keys()) if output_rows else []
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    turn_sources = set(turns_by_source)
    summary = {
        "segments_csv": args.segments_csv,
        "turns_csv": args.turns_csv,
        "output_csv": args.output_csv,
        "segment_rows": len(segments),
        "turn_rows": len(turns),
        "sources_with_segments": len(sources_with_segments),
        "turn_sources": len(turn_sources),
        "segments_mapped_to_at_least_one_turn": mapped_segments,
        "segments_without_overlapping_turn": len(segments) - mapped_segments,
        "segments_overlapping_multiple_turns": multi_turn_segments,
        "sources_without_diarization_segments": sorted(turn_sources - sources_with_segments),
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
