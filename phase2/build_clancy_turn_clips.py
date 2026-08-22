from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows
    from phase2.build_clancy_utterance_clips import _clean, _format_seconds, _time_to_seconds
    from phase2.trimodal_validation_utils import ffmpeg_exe
else:
    from .common import ensure_dir, read_csv_rows
    from .build_clancy_utterance_clips import _clean, _format_seconds, _time_to_seconds
    from .trimodal_validation_utils import ffmpeg_exe


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_turn_manifest.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/clancy/clancy_turn_manifest_clipped.csv")
DEFAULT_CLIP_ROOT = Path("data/processed/phase2/clancy/turn_clips")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_turn_clip_summary.json")
DEFAULT_ISSUES = Path("reports/phase2/clancy_turn_clip_issues.csv")
DEFAULT_SOURCE_OFFSETS = Path("data/processed/phase2/clancy/clancy_source_offsets.csv")


def _load_source_offsets(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    offsets: dict[str, float] = {}
    for row in read_csv_rows(path):
        youtube_id = _clean(row.get("youtube_id"))
        if not youtube_id:
            continue
        raw_offset = _clean(row.get("source_offset_seconds"))
        if not raw_offset:
            continue
        try:
            offsets[youtube_id] = max(0.0, float(raw_offset))
        except Exception:
            continue
    return offsets


def _source_offset(source_offsets: dict[str, float], youtube_id: str) -> tuple[float, str]:
    """Return an explicit offset or a documented zero default."""
    if youtube_id in source_offsets:
        return source_offsets[youtube_id], "explicit"
    return 0.0, "default_zero"


def _run_ffmpeg(src: Path, dest: Path, start: float, end: float, *, video: bool) -> None:
    ensure_dir(dest.parent)
    ffmpeg = ffmpeg_exe()
    duration = max(0.05, end - start)
    cmd = [ffmpeg, "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src)]
    if video:
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"])
    else:
        cmd.extend(["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"])
    cmd.append(str(dest))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create strict turn-level audio/video clips for the Clancy corpus")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--clip-root", default=str(DEFAULT_CLIP_ROOT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--issues-csv", default=str(DEFAULT_ISSUES))
    parser.add_argument("--source-offsets-csv", default=str(DEFAULT_SOURCE_OFFSETS))
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap for pilot runs")
    parser.add_argument("--include-youtube-ids", default="", help="Comma-separated youtube_id filter")
    parser.add_argument("--include-turn-ids", default="", help="Comma-separated turn_id filter")
    parser.add_argument("--start-padding-ms", type=int, default=0)
    parser.add_argument("--end-padding-ms", type=int, default=0)
    parser.add_argument("--min-clip-seconds", type=float, default=0.6)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_csv_rows(input_path)
    if not rows:
        raise SystemExit(f"No rows found in {input_path}")

    source_offsets = _load_source_offsets(Path(args.source_offsets_csv))
    include_youtube_ids = {s.strip() for s in args.include_youtube_ids.split(",") if s.strip()}
    include_turn_ids = {s.strip() for s in args.include_turn_ids.split(",") if s.strip()}
    if include_youtube_ids:
        rows = [row for row in rows if _clean(row.get("youtube_id")) in include_youtube_ids]
    if include_turn_ids:
        rows = [row for row in rows if _clean(row.get("turn_id")) in include_turn_ids]
    rows.sort(key=lambda row: (_clean(row.get("youtube_id")), _time_to_seconds(row.get("turn_start_time") or row.get("start_time")), _clean(row.get("turn_id"))))
    if args.max_rows and args.max_rows > 0:
        rows = rows[: args.max_rows]

    clip_root = Path(args.clip_root).resolve()
    video_root = ensure_dir(clip_root / "video")
    audio_root = ensure_dir(clip_root / "audio")
    output_csv = Path(args.output_csv)
    summary_json = Path(args.summary_json)
    issues_csv = Path(args.issues_csv)
    for path in [output_csv, summary_json, issues_csv]:
        ensure_dir(path.parent)

    output_rows: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    clip_counts = Counter()
    total_clip_seconds = 0.0

    for row in rows:
        turn_id = _clean(row.get("turn_id")) or _clean(row.get("utterance_id"))
        youtube_id = _clean(row.get("youtube_id"))
        start_raw = _clean(row.get("turn_start_time") or row.get("start_time"))
        end_raw = _clean(row.get("turn_end_time") or row.get("end_time"))
        src_video = Path(_clean(row.get("video_path")))
        src_audio = Path(_clean(row.get("audio_path")))
        source_offset_seconds, source_offset_status = _source_offset(source_offsets, youtube_id)

        if not turn_id or not youtube_id:
            issues.append({"issue": "missing_identity", "turn_id": turn_id, "youtube_id": youtube_id, "value": ""})
            continue
        if not src_video.exists():
            issues.append({"issue": "missing_source_video", "turn_id": turn_id, "youtube_id": youtube_id, "value": str(src_video)})
            continue
        if not src_audio.exists():
            src_audio = src_video

        start_seconds = max(0.0, source_offset_seconds + _time_to_seconds(start_raw) - args.start_padding_ms / 1000.0)
        end_seconds = max(start_seconds + args.min_clip_seconds, source_offset_seconds + _time_to_seconds(end_raw) + args.end_padding_ms / 1000.0)
        clip_duration_seconds = round(end_seconds - start_seconds, 3)

        video_dest = video_root / youtube_id / f"{turn_id}.mp4"
        audio_dest = audio_root / youtube_id / f"{turn_id}.wav"
        clip_status = "created"
        if args.skip_existing and video_dest.exists() and audio_dest.exists():
            clip_status = "reused"
        else:
            try:
                _run_ffmpeg(src_video, video_dest, start_seconds, end_seconds, video=True)
                _run_ffmpeg(src_audio, audio_dest, start_seconds, end_seconds, video=False)
            except subprocess.CalledProcessError as exc:
                clip_status = "failed"
                issues.append(
                    {
                        "issue": "ffmpeg_failed",
                        "turn_id": turn_id,
                        "youtube_id": youtube_id,
                        "value": exc.stderr.decode("utf-8", errors="ignore")[:500] if exc.stderr else "",
                    }
                )
                continue

        clip_counts[clip_status] += 1
        total_clip_seconds += clip_duration_seconds
        output_row = dict(row)
        output_row.update(
            {
                "source_video_path": str(src_video),
                "source_audio_path": str(src_audio),
                "clip_video_path": str(video_dest),
                "clip_audio_path": str(audio_dest),
                "video_path": str(video_dest),
                "audio_path": str(audio_dest),
                "duration_seconds": f"{clip_duration_seconds:.3f}",
                "clip_start_seconds": f"{start_seconds:.3f}",
                "clip_end_seconds": f"{end_seconds:.3f}",
                "clip_duration_seconds": f"{clip_duration_seconds:.3f}",
                "clip_status": clip_status,
                "start_time": _format_seconds(start_seconds),
                "end_time": _format_seconds(end_seconds),
                "utterance_id": turn_id,
                "utterance_text": _clean(row.get("turn_text") or row.get("utterance_text")),
                "source_offset_seconds": f"{source_offset_seconds:.3f}",
                "source_offset_status": source_offset_status,
            }
        )
        output_rows.append(output_row)

    if not output_rows:
        raise SystemExit("No turn clips were produced")

    fieldnames = list(output_rows[0].keys())
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    with issues_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["issue", "turn_id", "youtube_id", "value"])
        writer.writeheader()
        for item in issues:
            writer.writerow(
                {
                    "issue": item.get("issue", ""),
                    "turn_id": item.get("turn_id", ""),
                    "youtube_id": item.get("youtube_id", ""),
                    "value": item.get("value", ""),
                }
            )

    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_csv),
        "clip_root": str(clip_root),
        "source_offsets_csv": str(Path(args.source_offsets_csv)),
        "offset_default_rule": "Missing, blank, invalid, or unlisted source offsets use 0.000 seconds.",
        "source_offset_status_counts": dict(Counter(row.get("source_offset_status", "") for row in output_rows)),
        "total_input_rows": len(rows),
        "rows_written": len(output_rows),
        "clips_created": int(clip_counts.get("created", 0)),
        "clips_reused": int(clip_counts.get("reused", 0)),
        "clips_failed": int(clip_counts.get("failed", 0)),
        "issues_count": len(issues),
        "total_clip_hours": round(total_clip_seconds / 3600.0, 4),
        "split_counts": dict(Counter(row.get("split", "") for row in output_rows)),
        "status": "PASS" if output_rows and not any(item["issue"] == "ffmpeg_failed" for item in issues) else "WARN",
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
