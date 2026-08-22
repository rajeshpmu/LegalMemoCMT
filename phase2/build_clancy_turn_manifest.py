from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows
else:
    from .common import ensure_dir, read_csv_rows


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_training_manifest_weak.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/clancy/clancy_turn_manifest.csv")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_turn_manifest_summary.json")
DEFAULT_ISSUES = Path("reports/phase2/clancy_turn_manifest_issues.csv")
DEFAULT_REJECTIONS = Path("data/processed/phase2/clancy/clancy_turn_rejection_manifest.csv")
TURN_MARKER = ">>"
WORD_RE = re.compile(r"[A-Za-z0-9']+")
MARKER_SPLIT_RE = re.compile(r"\s*>>\s*")
CONTINUATION_STARTERS = {
    "all right",
    "alright",
    "okay",
    "ok",
    "well",
    "so",
    "um",
    "uh",
    "and",
    "then",
    "now",
    "right",
    "good morning",
    "good afternoon",
    "good evening",
}
SHORT_REPLY_WORDS = {"yes", "no", "okay", "ok", "sure", "right", "good", "thank you", "thanks"}


def _clean(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _time_to_seconds(value: object) -> float:
    text = _clean(value)
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


def _tokens(text: str) -> list[str]:
    return WORD_RE.findall(_clean(text).lower())


def _merge_text(left: str, right: str) -> str:
    left = _clean(left)
    right = _clean(right)
    if not left:
        return right
    if not right:
        return left

    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens:
        return right
    if not right_tokens:
        return left

    if left_tokens == right_tokens:
        return right if len(right) >= len(left) else left
    if len(left_tokens) < len(right_tokens) and right_tokens[: len(left_tokens)] == left_tokens:
        return right
    if len(right_tokens) < len(left_tokens) and left_tokens[: len(right_tokens)] == right_tokens:
        return left

    max_overlap = min(len(left_tokens), len(right_tokens))
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if left_tokens[-size:] == right_tokens[:size]:
            overlap = size
            break
    if overlap:
        right_matches = list(WORD_RE.finditer(right))
        if overlap < len(right_matches):
            remainder = right[right_matches[overlap].start():].lstrip()
        else:
            remainder = ""
        if remainder:
            separator = "" if left.endswith((" ", "\n", "\t")) else " "
            return f"{left}{separator}{remainder}".strip()
        return left

    return f"{left} {right}"


def _split_turn_segments(text: str) -> list[str]:
    parts = [part.strip() for part in MARKER_SPLIT_RE.split(_clean(text)) if part.strip()]
    if not parts:
        return [""]
    return parts


def _normalized_prefix(text: str, word_limit: int = 3) -> str:
    tokens = _tokens(text)
    return " ".join(tokens[:word_limit])


def _is_short_reply(text: str) -> bool:
    norm = _normalized_prefix(text, 3)
    return norm in SHORT_REPLY_WORDS or len(_tokens(text)) <= 2


def _looks_like_continuation(text: str) -> bool:
    norm = _normalized_prefix(text, 3)
    return norm in CONTINUATION_STARTERS


def _texts_overlap_or_match(left: str, right: str) -> bool:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    if len(left_tokens) < len(right_tokens) and right_tokens[: len(left_tokens)] == left_tokens:
        return True
    if len(right_tokens) < len(left_tokens) and left_tokens[: len(right_tokens)] == right_tokens:
        return True
    max_overlap = min(len(left_tokens), len(right_tokens))
    for size in range(max_overlap, 1, -1):
        if left_tokens[-size:] == right_tokens[:size]:
            return True
    return False


def _allocate_segment_spans(start: float, end: float, segments: list[str]) -> list[tuple[float, float]]:
    duration = max(end - start, 0.01)
    weights = [max(len(_tokens(segment)), 1) for segment in segments]
    total = sum(weights) or len(segments)
    spans: list[tuple[float, float]] = []
    cursor = start
    for idx, weight in enumerate(weights):
        if idx == len(weights) - 1:
            seg_end = end
        else:
            seg_end = cursor + duration * (weight / total)
        spans.append((cursor, max(cursor, seg_end)))
        cursor = max(cursor, seg_end)
    return spans


def _build_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], Counter]:
    turns: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    stats: Counter = Counter()

    current: dict[str, str] | None = None
    current_turn_index = 0

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        current["turn_source_utterance_ids"] = ",".join(current.pop("_source_ids", []))
        current["turn_source_utterance_count"] = str(len(current["turn_source_utterance_ids"].split(",")) if current["turn_source_utterance_ids"] else 0)
        current["turn_piece_ids"] = ",".join(current.pop("_piece_ids", []))
        current["turn_piece_count"] = str(current.pop("_piece_count", 0))
        current["turn_start_time"] = _format_seconds(_time_to_seconds(current["turn_start_time"]))
        current["turn_end_time"] = _format_seconds(_time_to_seconds(current["turn_end_time"]))
        current["turn_duration_seconds"] = f"{max(_time_to_seconds(current['turn_end_time']) - _time_to_seconds(current['turn_start_time']), 0.0):.3f}"
        current["duration_seconds"] = current["turn_duration_seconds"]
        current["utterance_text"] = _clean(current.get("turn_text"))
        current["turn_id"] = _clean(current.get("turn_id"))
        current["utterance_id"] = current["turn_id"]
        turns.append({k: v for k, v in current.items() if not k.startswith("_")})
        current = None

    for row in rows:
        row = dict(row)
        text = _clean(row.get("utterance_text"))
        if not text:
            issues.append(
                {
                    "issue": "empty_text",
                    "youtube_id": _clean(row.get("youtube_id")),
                    "utterance_id": _clean(row.get("utterance_id")),
                    "value": "",
                }
            )
            continue

        row_start = _time_to_seconds(row.get("start_time"))
        row_end = _time_to_seconds(row.get("end_time"))
        row_source_id = _clean(row.get("utterance_id"))
        row_marker_count = text.count(TURN_MARKER)
        row_starts_with_marker = text.lstrip().startswith(TURN_MARKER)
        segments = _split_turn_segments(text)
        spans = _allocate_segment_spans(row_start, row_end, segments)

        for seg_index, (segment_text, (seg_start, seg_end)) in enumerate(zip(segments, spans), start=1):
            segment_text = _clean(segment_text)
            if not segment_text:
                continue
            starts_new_turn = current is None or row_starts_with_marker or seg_index > 1
            if starts_new_turn:
                flush()
                current_turn_index += 1
                current = {
                    "turn_id": f"{_clean(row.get('youtube_id'))}_turn{current_turn_index:05d}",
                    "youtube_id": _clean(row.get("youtube_id")),
                    "source_url": _clean(row.get("source_url")),
                    "title": _clean(row.get("title")),
                    "category": _clean(row.get("category")),
                    "priority": _clean(row.get("priority")),
                    "subtitle_path": _clean(row.get("subtitle_path")),
                    "video_path": _clean(row.get("video_path")),
                    "audio_path": _clean(row.get("audio_path")),
                    "split_group_id": _clean(row.get("split_group_id")),
                    "split_strategy": _clean(row.get("split_strategy")),
                    "split": _clean(row.get("split")),
                    "emotion_label": _clean(row.get("emotion_label")),
                    "emotion_label_source": _clean(row.get("emotion_label_source")),
                    "emotion_label_confidence": _clean(row.get("emotion_label_confidence")),
                    "review_flag": _clean(row.get("review_flag")),
                    "review_reason": _clean(row.get("review_reason")),
                    "usable_for_phase2": _clean(row.get("usable_for_phase2")),
                    "turn_start_time": _format_seconds(seg_start),
                    "turn_end_time": _format_seconds(seg_end),
                    "turn_text": segment_text,
                    "turn_boundary_type": "marker" if (row_starts_with_marker or seg_index > 1) else "initial",
                    "turn_confidence": "HIGH" if (row_starts_with_marker or row_marker_count > 0) else "MEDIUM",
                    "turn_marker_count": "1" if (row_starts_with_marker or seg_index > 1) else "0",
                    "_source_ids": [row_source_id] if row_source_id else [],
                    "_piece_ids": [f"{row_source_id}#p{seg_index:02d}"] if row_source_id else [],
                    "_piece_count": 1,
                }
            else:
                current["turn_end_time"] = _format_seconds(seg_end)
                current["turn_text"] = _merge_text(current.get("turn_text", ""), segment_text)
                current["_source_ids"].append(row_source_id)
                current["_piece_ids"].append(f"{row_source_id}#p{seg_index:02d}")
                current["_piece_count"] = int(current["_piece_count"]) + 1
                current["turn_confidence"] = "MEDIUM" if current.get("turn_confidence") != "LOW" else "LOW"

            stats["source_rows_seen"] += 1
            if row_marker_count:
                stats["rows_with_turn_markers"] += 1
            if seg_index > 1:
                stats["embedded_turn_segments"] += 1

        if current is not None:
            current["turn_boundary_type"] = current.get("turn_boundary_type") or "continuation"

    flush()
    turns = _consolidate_turns(turns, stats)
    return turns, issues, stats


def _load_rejections(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {
            _clean(row.get("turn_id")): _clean(row.get("rejection_reason"))
            for row in csv.DictReader(f)
            if _clean(row.get("turn_id"))
        }


def _apply_rejections(turns: list[dict[str, str]], rejection_path: Path, stats: Counter) -> list[dict[str, str]]:
    rejected = _load_rejections(rejection_path)
    if not rejected:
        return turns
    kept = []
    for row in turns:
        turn_id = _clean(row.get("turn_id"))
        if turn_id not in rejected:
            kept.append(row)
            continue
        row["usable_for_phase2"] = "NO"
        row["review_flag"] = "YES"
        row["review_reason"] = rejected[turn_id]
        stats["rejected_by_manifest"] += 1
    return kept


def _consolidate_turns(turns: list[dict[str, str]], stats: Counter) -> list[dict[str, str]]:
    if not turns:
        return turns
    merged: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            merged.append(current)
            current = None

    for row in turns:
        row = dict(row)
        if current is None:
            current = row
            continue

        current_youtube = _clean(current.get("youtube_id"))
        row_youtube = _clean(row.get("youtube_id"))
        gap = _time_to_seconds(row.get("turn_start_time")) - _time_to_seconds(current.get("turn_end_time"))
        current_text = _clean(current.get("turn_text"))
        row_text = _clean(row.get("turn_text"))
        current_token_count = len(_tokens(current_text))
        row_token_count = len(_tokens(row_text))
        same_sequence = current_youtube == row_youtube and gap <= 1.0
        can_merge = False

        if same_sequence:
            if _texts_overlap_or_match(current_text, row_text):
                can_merge = True
            elif _looks_like_continuation(row_text) and row_token_count >= 3 and not _is_short_reply(row_text):
                if current_token_count <= 8 or current.get("turn_boundary_type") == "marker":
                    can_merge = True
            elif not _is_short_reply(row_text) and not _is_short_reply(current_text):
                if current_token_count <= 6 or current_text.endswith((".", "?", "!")):
                    if _looks_like_continuation(row_text) or row_text[:1].islower() or row_text.startswith(">>"):
                        can_merge = True

        if not can_merge:
            flush()
            current = row
            continue

        current["turn_text"] = _merge_text(current_text, row_text)
        current["turn_end_time"] = row.get("turn_end_time", current.get("turn_end_time", ""))
        current["turn_duration_seconds"] = f"{max(_time_to_seconds(current['turn_end_time']) - _time_to_seconds(current['turn_start_time']), 0.0):.3f}"
        current["duration_seconds"] = current["turn_duration_seconds"]
        current["turn_source_utterance_ids"] = ",".join(
            [s for s in [current.get("turn_source_utterance_ids", ""), row.get("turn_source_utterance_ids", "")] if s]
        )
        current_sources = [s for s in current.get("turn_source_utterance_ids", "").split(",") if s]
        row_sources = [s for s in row.get("turn_source_utterance_ids", "").split(",") if s]
        current["turn_source_utterance_ids"] = ",".join(dict.fromkeys(current_sources + row_sources))
        current["turn_source_utterance_count"] = str(len([s for s in current["turn_source_utterance_ids"].split(",") if s]))
        current_pieces = [s for s in current.get("turn_piece_ids", "").split(",") if s]
        row_pieces = [s for s in row.get("turn_piece_ids", "").split(",") if s]
        current["turn_piece_ids"] = ",".join(dict.fromkeys(current_pieces + row_pieces))
        current["turn_piece_count"] = str(len([s for s in current["turn_piece_ids"].split(",") if s]))
        current["turn_confidence"] = "MEDIUM" if current.get("turn_confidence") != "LOW" else "LOW"
        stats["consolidated_turn_pairs"] += 1

    flush()
    for idx, row in enumerate(merged, start=1):
        row["turn_id"] = f"{_clean(row.get('youtube_id'))}_turn{idx:05d}"
        row["utterance_id"] = row["turn_id"]
    stats["consolidated_turn_rows"] = len(merged)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a turn-based Clancy manifest from subtitle cue rows")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--issues-csv", default=str(DEFAULT_ISSUES))
    parser.add_argument("--rejection-csv", default=str(DEFAULT_REJECTIONS))
    parser.add_argument("--include-splits", default="", help="Comma-separated split filter")
    parser.add_argument("--include-youtube-ids", default="", help="Comma-separated youtube_id filter")
    parser.add_argument("--include-utterance-ids", default="", help="Comma-separated utterance_id filter")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap for pilot runs")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_csv_rows(input_path)
    if not rows:
        raise SystemExit(f"No rows found in {input_path}")

    include_splits = {s.strip().lower() for s in args.include_splits.split(",") if s.strip()}
    include_youtube_ids = {s.strip() for s in args.include_youtube_ids.split(",") if s.strip()}
    include_utterance_ids = {s.strip() for s in args.include_utterance_ids.split(",") if s.strip()}
    if include_splits:
        rows = [row for row in rows if _clean(row.get("split")).lower() in include_splits]
    if include_youtube_ids:
        rows = [row for row in rows if _clean(row.get("youtube_id")) in include_youtube_ids]
    if include_utterance_ids:
        rows = [row for row in rows if _clean(row.get("utterance_id")) in include_utterance_ids]
    rows.sort(key=lambda row: (_clean(row.get("youtube_id")), _time_to_seconds(row.get("start_time")), _clean(row.get("utterance_id"))))
    if args.max_rows and args.max_rows > 0:
        rows = rows[: args.max_rows]

    turns, issues, stats = _build_rows(rows)
    turns = _apply_rejections(turns, Path(args.rejection_csv), stats)
    if not turns:
        raise SystemExit("No turn rows were produced")

    output_path = Path(args.output_csv)
    summary_path = Path(args.summary_json)
    issues_path = Path(args.issues_csv)
    ensure_dir(output_path.parent)
    ensure_dir(summary_path.parent)
    ensure_dir(issues_path.parent)

    field_order = [
        "turn_id",
        "utterance_id",
        "youtube_id",
        "source_url",
        "title",
        "category",
        "priority",
        "subtitle_path",
        "video_path",
        "audio_path",
        "split_group_id",
        "split_strategy",
        "split",
        "emotion_label",
        "emotion_label_source",
        "emotion_label_confidence",
        "review_flag",
        "review_reason",
        "usable_for_phase2",
        "turn_text",
        "utterance_text",
        "turn_start_time",
        "turn_end_time",
        "turn_duration_seconds",
        "duration_seconds",
        "turn_boundary_type",
        "turn_confidence",
        "turn_marker_count",
        "turn_piece_count",
        "turn_piece_ids",
        "turn_source_utterance_ids",
        "turn_source_utterance_count",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        writer.writeheader()
        writer.writerows(turns)

    with issues_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["issue", "youtube_id", "utterance_id", "value"])
        writer.writeheader()
        writer.writerows(issues)

    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "issues_csv": str(issues_path),
        "rejection_csv": str(Path(args.rejection_csv)),
        "rejected_by_manifest": int(stats.get("rejected_by_manifest", 0)),
        "total_input_rows": len(rows),
        "turn_rows_written": len(turns),
        "source_rows_seen": int(stats.get("source_rows_seen", 0)),
        "rows_with_turn_markers": int(stats.get("rows_with_turn_markers", 0)),
        "embedded_turn_segments": int(stats.get("embedded_turn_segments", 0)),
        "unique_youtube_ids": len({row.get("youtube_id", "") for row in turns if row.get("youtube_id")}),
        "status": "PASS" if turns else "WARN",
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
