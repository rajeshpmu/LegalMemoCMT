from __future__ import annotations

import argparse
import csv
import json
import html
import re
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows
else:
    from .common import ensure_dir, read_csv_rows


DEFAULT_RAW_ROOT = Path("data/phase2/clancy/corpus/raw")
DEFAULT_SOURCE_MANIFEST = Path("data/processed/phase2/clancy/clancy_source_manifest.csv")
DEFAULT_OUTPUT_CSV = Path("data/processed/phase2/clancy/clancy_utterance_manifest.csv")
DEFAULT_SUMMARY_JSON = Path("reports/phase2/clancy_utterance_summary.json")

TIMESTAMP_RE = re.compile(r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})")
VIDEO_ID_RE = re.compile(r"([A-Za-z0-9_-]{11})(?:\.[a-z]{2,3})?$")
TAG_RE = re.compile(r"<[^>]+>")


def _time_to_seconds(ts: str) -> float:
    hours, minutes, rest = ts.split(":")
    seconds, millis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def _read_vtt(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    cues: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.upper().startswith("WEBVTT"):
            i += 1
            continue
        match = TIMESTAMP_RE.search(line)
        if not match:
            i += 1
            continue
        start = match.group("start")
        end = match.group("end")
        i += 1
        text_lines: list[str] = []
        while i < len(lines):
            current = lines[i].rstrip()
            if not current.strip():
                break
            if TIMESTAMP_RE.search(current):
                break
            if current.strip().upper().startswith(("NOTE", "STYLE", "REGION")):
                break
            text_lines.append(current.strip())
            i += 1
        text = " ".join(text_lines).strip()
        text = html.unescape(text)
        text = TAG_RE.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        cues.append(
            {
                "start_time": start,
                "end_time": end,
                "utterance_text": text,
            }
        )
        while i < len(lines) and lines[i].strip():
            i += 1
        i += 1
    return cues


def _build_source_map(source_manifest: Path) -> dict[str, dict[str, str]]:
    if not source_manifest.exists():
        return {}
    rows = read_csv_rows(source_manifest)
    mapping: dict[str, dict[str, str]] = {}
    for row in rows:
        youtube_id = row.get("youtube_id", "").strip()
        if youtube_id:
            mapping[youtube_id] = row
    return mapping


def _derive_source_info(vtt_path: Path, source_map: dict[str, dict[str, str]]) -> dict[str, str]:
    stem = vtt_path.stem
    base_stem = re.sub(r"\.[a-z]{2,3}$", "", stem)
    match = VIDEO_ID_RE.search(base_stem)
    youtube_id = match.group(1) if match else base_stem.split("_")[-1]
    source = source_map.get(youtube_id, {})
    return {
        "youtube_id": youtube_id,
        "source_url": source.get("source_url", ""),
        "title": source.get("title", ""),
        "category": source.get("category", ""),
        "priority": source.get("priority", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build utterance-level rows from Clancy subtitle files")
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT), help="Root directory containing Clancy raw media folders")
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST), help="Clancy source manifest for URL/title mapping")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV), help="Utterance manifest output CSV")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON), help="Utterance summary JSON")
    parser.add_argument("--min-text-length", type=int, default=2, help="Minimum text length to keep a subtitle cue")
    parser.add_argument("--skip-empty", action="store_true", help="Skip empty subtitle cues entirely")
    args = parser.parse_args()

    raw_root = Path(args.raw_root)
    source_manifest = Path(args.source_manifest)
    output_csv = Path(args.output_csv)
    summary_json = Path(args.summary_json)
    ensure_dir(output_csv.parent)
    ensure_dir(summary_json.parent)

    source_map = _build_source_map(source_manifest)
    vtt_files = sorted(raw_root.rglob("*.vtt"))

    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "raw_root": str(raw_root),
        "source_manifest": str(source_manifest),
        "vtt_files": len(vtt_files),
        "utterances_total": 0,
        "utterances_kept": 0,
        "utterances_skipped_empty": 0,
        "files_with_cues": 0,
        "files_without_cues": 0,
    }

    for vtt_path in vtt_files:
        source_info = _derive_source_info(vtt_path, source_map)
        cues = _read_vtt(vtt_path)
        if not cues:
            summary["files_without_cues"] = int(summary["files_without_cues"]) + 1
            continue
        summary["files_with_cues"] = int(summary["files_with_cues"]) + 1

        media_stem = re.sub(r"\.[a-z]{2,3}$", "", vtt_path.stem)
        mp4_path = vtt_path.with_name(media_stem + ".mp4")
        wav_path = vtt_path.with_name(media_stem + ".wav")
        base_id = source_info["youtube_id"] or vtt_path.stem.split("_")[-1]
        for idx, cue in enumerate(cues, start=1):
            text = cue["utterance_text"].strip()
            summary["utterances_total"] = int(summary["utterances_total"]) + 1
            if not text and args.skip_empty:
                summary["utterances_skipped_empty"] = int(summary["utterances_skipped_empty"]) + 1
                continue
            if len(text) < args.min_text_length:
                summary["utterances_skipped_empty"] = int(summary["utterances_skipped_empty"]) + 1
                continue
            start_seconds = _time_to_seconds(cue["start_time"])
            end_seconds = _time_to_seconds(cue["end_time"])
            rows.append(
                {
                    "utterance_id": f"{base_id}_utt{idx:05d}",
                    "youtube_id": source_info["youtube_id"],
                    "source_url": source_info["source_url"],
                    "title": source_info["title"],
                    "category": source_info["category"],
                    "priority": source_info["priority"],
                    "subtitle_path": str(vtt_path),
                    "video_path": str(mp4_path) if mp4_path.exists() else "",
                    "audio_path": str(wav_path) if wav_path.exists() else "",
                    "cue_index": idx,
                    "start_time": cue["start_time"],
                    "end_time": cue["end_time"],
                    "duration_seconds": round(max(end_seconds - start_seconds, 0.0), 3),
                    "utterance_text": text,
                    "usable_for_phase2": "YES" if mp4_path.exists() and wav_path.exists() else "NO",
                }
            )
            summary["utterances_kept"] = int(summary["utterances_kept"]) + 1

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "utterance_id",
                "youtube_id",
                "source_url",
                "title",
                "category",
                "priority",
                "subtitle_path",
                "video_path",
                "audio_path",
                "cue_index",
                "start_time",
                "end_time",
                "duration_seconds",
                "utterance_text",
                "usable_for_phase2",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary["output_csv"] = str(output_csv)
    summary["rows_written"] = len(rows)
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(rows)} Clancy utterance rows to {output_csv}")
    print(f"Wrote summary to {summary_json}")


if __name__ == "__main__":
    main()
