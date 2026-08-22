from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows
    from phase2.trimodal_validation_utils import ffmpeg_exe
else:
    from .common import ensure_dir, read_csv_rows
    from .trimodal_validation_utils import ffmpeg_exe


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_training_manifest_weak.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/clancy/clancy_training_manifest_clipped.csv")
DEFAULT_CLIP_ROOT = Path("data/processed/phase2/clancy/utterance_clips")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_utterance_clip_summary.json")
DEFAULT_ISSUES = Path("reports/phase2/clancy_utterance_clip_issues.csv")
DEFAULT_SOURCE_OFFSETS = Path("data/processed/phase2/clancy/clancy_source_offsets.csv")
MIN_FRAGMENT_SECONDS = 0.45
MAX_FRAGMENT_GAP_SECONDS = 0.20
WORD_RE = re.compile(r"[A-Za-z0-9']+")


def _time_to_seconds(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    parts = text.split(":")
    if len(parts) != 3:
        try:
            return float(text)
        except Exception:
            return 0.0
    hours = int(parts[0])
    minutes = int(parts[1])
    sec_part = parts[2]
    if "." in sec_part:
        seconds, millis = sec_part.split(".", 1)
        ms = (millis + "000")[:3]
    else:
        seconds, ms = sec_part, "000"
    return hours * 3600 + minutes * 60 + int(seconds) + int(ms) / 1000.0


def _format_seconds(value: float) -> str:
    if value < 0:
        value = 0.0
    whole = int(value)
    hours, rem = divmod(whole, 3600)
    minutes, seconds = divmod(rem, 60)
    millis = int(round((value - whole) * 1000))
    if millis >= 1000:
        seconds += 1
        millis -= 1000
    if seconds >= 60:
        minutes += 1
        seconds -= 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


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


def _clean(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


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


def _duration_seconds(value: object) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except Exception:
        return 0.0


def _word_tokens(text: object) -> list[str]:
    return WORD_RE.findall(_clean(text).lower())


def _text_relation(left: object, right: object) -> str:
    left_tokens = _word_tokens(left)
    right_tokens = _word_tokens(right)
    if not left_tokens or not right_tokens:
        return ""
    if left_tokens == right_tokens:
        return "same"
    if len(left_tokens) < len(right_tokens) and right_tokens[: len(left_tokens)] == left_tokens:
        return "left_prefix"
    if len(right_tokens) < len(left_tokens) and left_tokens[: len(right_tokens)] == right_tokens:
        return "right_prefix"
    return ""


def _looks_fragment(text: str, duration_seconds: float) -> bool:
    stripped = _clean(text)
    if not stripped:
        return True
    if duration_seconds < MIN_FRAGMENT_SECONDS:
        return True
    if len(stripped) < 18:
        return True
    return not stripped.endswith((".", "?", "!"))


def _merge_source_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    current_ids: list[str] = []
    current_source_seconds = 0.0

    def flush() -> None:
        nonlocal current, current_ids, current_source_seconds
        if current is None:
            return
        out = dict(current)
        out["source_utterance_ids"] = ",".join(current_ids)
        out["source_utterance_count"] = str(len(current_ids))
        out["source_duration_seconds"] = f"{current_source_seconds:.3f}"
        out["duration_seconds"] = f"{max(_time_to_seconds(out.get('end_time')) - _time_to_seconds(out.get('start_time')), 0.0):.3f}"
        merged.append(out)
        current = None
        current_ids = []
        current_source_seconds = 0.0

    for row in rows:
        row = dict(row)
        row_source_seconds = _duration_seconds(row.get("duration_seconds"))
        row["source_duration_seconds"] = f"{row_source_seconds:.3f}"
        row_start = _time_to_seconds(row.get("start_time"))
        row_end = _time_to_seconds(row.get("end_time"))
        row_text = _clean(row.get("utterance_text"))
        row_id = _clean(row.get("utterance_id"))

        if current is None:
            current = row
            current_ids = [row_id]
            current_source_seconds = row_source_seconds
            continue

        current_youtube = _clean(current.get("youtube_id"))
        row_youtube = _clean(row.get("youtube_id"))
        current_end = _time_to_seconds(current.get("end_time"))
        current_start = _time_to_seconds(current.get("start_time"))
        current_text = _clean(current.get("utterance_text"))
        gap = row_start - current_end
        relation = _text_relation(current_text, row_text)
        should_merge = current_youtube == row_youtube and gap <= MAX_FRAGMENT_GAP_SECONDS and relation in {"same", "left_prefix", "right_prefix"}

        if not should_merge:
            flush()
            current = row
            current_ids = [row_id]
            current_source_seconds = row_source_seconds
            continue

        if relation == "left_prefix":
            merged_row = dict(row)
            merged_row["start_time"] = current.get("start_time", row.get("start_time", ""))
            merged_row["end_time"] = _format_seconds(max(current_end, row_end))
            merged_row["duration_seconds"] = f"{max(_time_to_seconds(merged_row['end_time']) - _time_to_seconds(merged_row['start_time']), 0.0):.3f}"
            merged_row["utterance_text"] = row_text
            current = merged_row
        else:
            current["start_time"] = _format_seconds(min(current_start, row_start))
            current["end_time"] = _format_seconds(max(current_end, row_end))
            current["duration_seconds"] = f"{max(_time_to_seconds(current['end_time']) - _time_to_seconds(current['start_time']), 0.0):.3f}"
            if relation == "same":
                current["utterance_text"] = row_text if len(row_text) >= len(current_text) else current_text
            current_source_seconds += row_source_seconds
            current_ids.append(row_id)
            continue

        current_source_seconds += row_source_seconds
        current_ids.append(row_id)

    flush()
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Create utterance-level audio/video clips for the Clancy corpus")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--clip-root", default=str(DEFAULT_CLIP_ROOT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--issues-csv", default=str(DEFAULT_ISSUES))
    parser.add_argument("--source-offsets-csv", default=str(DEFAULT_SOURCE_OFFSETS))
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap for pilot runs")
    parser.add_argument("--include-splits", default="", help="Comma-separated split filter")
    parser.add_argument("--include-youtube-ids", default="", help="Comma-separated youtube_id filter")
    parser.add_argument("--include-utterance-ids", default="", help="Comma-separated utterance_id filter")
    parser.add_argument(
        "--neighbor-window",
        type=int,
        default=0,
        help="When include-utterance-ids is used, also include this many neighboring cues on each side",
    )
    parser.add_argument("--start-padding-ms", type=int, default=1000)
    parser.add_argument("--end-padding-ms", type=int, default=350)
    parser.add_argument("--min-clip-seconds", type=float, default=0.8)
    parser.add_argument(
        "--strict-boundaries",
        action="store_true",
        help="Clip exactly to the utterance span and ignore contextual padding.",
    )
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_csv_rows(input_path)
    if not rows:
        raise SystemExit(f"No rows found in {input_path}")

    source_offsets = _load_source_offsets(Path(args.source_offsets_csv))
    include_splits = {s.strip().lower() for s in args.include_splits.split(",") if s.strip()}
    include_youtube_ids = {s.strip() for s in args.include_youtube_ids.split(",") if s.strip()}
    include_utterance_ids = {s.strip() for s in args.include_utterance_ids.split(",") if s.strip()}
    if include_splits:
        rows = [row for row in rows if _clean(row.get("split")).lower() in include_splits]
    if include_youtube_ids:
        rows = [row for row in rows if _clean(row.get("youtube_id")) in include_youtube_ids]
    rows.sort(key=lambda row: (_clean(row.get("youtube_id")), _clean(row.get("start_time")), _clean(row.get("utterance_id"))))
    if include_utterance_ids:
        selected_positions = [i for i, row in enumerate(rows) if _clean(row.get("utterance_id")) in include_utterance_ids]
        if args.neighbor_window > 0 and selected_positions:
            expanded_positions: set[int] = set()
            for pos in selected_positions:
                lo = max(0, pos - args.neighbor_window)
                hi = min(len(rows), pos + args.neighbor_window + 1)
                for idx in range(lo, hi):
                    if _clean(rows[idx].get("youtube_id")) == _clean(rows[pos].get("youtube_id")):
                        expanded_positions.add(idx)
            rows = [rows[i] for i in sorted(expanded_positions)]
        else:
            rows = [row for row in rows if _clean(row.get("utterance_id")) in include_utterance_ids]
    rows = _merge_source_rows(rows)
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
        utterance_id = _clean(row.get("utterance_id"))
        youtube_id = _clean(row.get("youtube_id"))
        start_raw = _clean(row.get("start_time"))
        end_raw = _clean(row.get("end_time"))
        src_video = Path(_clean(row.get("video_path")))
        src_audio = Path(_clean(row.get("audio_path")))
        source_offset_seconds, source_offset_status = _source_offset(source_offsets, youtube_id)

        if not utterance_id or not youtube_id:
            issues.append({"issue": "missing_identity", "utterance_id": utterance_id, "youtube_id": youtube_id, "value": ""})
            continue
        if not src_video.exists():
            issues.append({"issue": "missing_source_video", "utterance_id": utterance_id, "youtube_id": youtube_id, "value": str(src_video)})
            continue
        if not src_audio.exists():
            src_audio = src_video

        start_seconds = _time_to_seconds(start_raw)
        end_seconds = _time_to_seconds(end_raw)
        start_padding_ms = 0 if args.strict_boundaries else args.start_padding_ms
        end_padding_ms = 0 if args.strict_boundaries else args.end_padding_ms
        start_seconds = max(0.0, source_offset_seconds + start_seconds - start_padding_ms / 1000.0)
        end_seconds = max(start_seconds + args.min_clip_seconds, source_offset_seconds + end_seconds + end_padding_ms / 1000.0)
        clip_duration_seconds = round(end_seconds - start_seconds, 3)

        video_dest = video_root / youtube_id / f"{utterance_id}.mp4"
        audio_dest = audio_root / youtube_id / f"{utterance_id}.wav"
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
                        "utterance_id": utterance_id,
                        "youtube_id": youtube_id,
                        "value": exc.stderr.decode("utf-8", errors="ignore")[:500] if exc.stderr else "",
                    }
                )
                continue

        clip_counts[clip_status] += 1
        total_clip_seconds += clip_duration_seconds
        video_path = str(video_dest)
        audio_path = str(audio_dest)
        output_row = dict(row)
        output_row.update(
            {
                "source_video_path": str(src_video),
                "source_audio_path": str(src_audio),
                "clip_video_path": video_path,
                "clip_audio_path": audio_path,
                "video_path": video_path,
                "audio_path": audio_path,
                "duration_seconds": f"{clip_duration_seconds:.3f}",
                "clip_start_seconds": f"{start_seconds:.3f}",
                "clip_end_seconds": f"{end_seconds:.3f}",
                "clip_duration_seconds": f"{clip_duration_seconds:.3f}",
                "clip_status": clip_status,
                "start_time": _format_seconds(start_seconds),
                "end_time": _format_seconds(end_seconds),
                "source_offset_seconds": f"{source_offset_seconds:.3f}",
                "source_offset_status": source_offset_status,
            }
        )
        output_rows.append(output_row)

    if not output_rows:
        raise SystemExit("No utterance clips were produced")

    fieldnames = list(output_rows[0].keys())
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    with issues_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["issue", "utterance_id", "youtube_id", "value"])
        writer.writeheader()
        for item in issues:
            writer.writerow(
                {
                    "issue": item.get("issue", ""),
                    "utterance_id": item.get("utterance_id", ""),
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
