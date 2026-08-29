"""Select Clancy pseudo-label rows for targeted manual review."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from textwrap import shorten


def clean(value: object) -> str:
    return str(value or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument(
        "--max-confidence",
        type=float,
        default=None,
        help="Select rows at or below this predicted-label confidence.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Select rows at or above this predicted-label confidence.",
    )
    parser.add_argument(
        "--emotion",
        action="append",
        default=[],
        help="Select a predicted emotion; repeat or use comma-separated values.",
    )
    parser.add_argument("--source", action="append", default=[], help="Filter by youtube_id; repeat or use comma-separated values.")
    parser.add_argument("--split", action="append", default=[], help="Filter by split; repeat or use comma-separated values.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum selected rows; 0 means no limit.")
    parser.add_argument("--print-rows", type=int, default=0, help="Pretty-print the first N selected rows after writing the CSV.")
    args = parser.parse_args()

    if args.min_confidence is not None and args.max_confidence is not None and args.min_confidence > args.max_confidence:
        raise SystemExit("--min-confidence cannot be greater than --max-confidence")

    def expand(values: list[str]) -> set[str]:
        return {part.strip().lower() for value in values for part in value.split(",") if part.strip()}

    emotions = expand(args.emotion)
    sources = expand(args.source)
    splits = expand(args.split)

    input_path = Path(args.input_csv)
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"No rows found in {input_path}")

    required = {"utterance_id", "phase1_basic_emotion", "phase1_basic_emotion_confidence"}
    missing = sorted(required - set(rows[0]))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")

    selected: list[dict[str, str]] = []
    reasons: Counter[str] = Counter()
    for row in rows:
        try:
            confidence = float(clean(row.get("phase1_basic_emotion_confidence")))
        except ValueError:
            confidence = -1.0
        emotion = clean(row.get("phase1_basic_emotion")).lower()
        source = clean(row.get("youtube_id")).lower()
        split = clean(row.get("split")).lower()
        row_reasons = []
        if args.max_confidence is not None and confidence <= args.max_confidence:
            row_reasons.append(f"confidence<={args.max_confidence:g}")
        elif args.max_confidence is not None:
            continue
        if args.min_confidence is not None and confidence >= args.min_confidence:
            row_reasons.append(f"confidence>={args.min_confidence:g}")
        elif args.min_confidence is not None:
            continue
        if emotions and emotion in emotions:
            row_reasons.append("emotion=" + emotion)
        elif emotions:
            continue
        if sources and source in sources:
            row_reasons.append("source=" + source)
        elif sources:
            continue
        if splits and split in splits:
            row_reasons.append("split=" + split)
        elif splits:
            continue
        if not row_reasons:
            raise SystemExit("Provide at least one selection criterion")
        enriched = dict(row)
        enriched["review_selection_reason"] = "; ".join(row_reasons)
        selected.append(enriched)
        reasons[enriched["review_selection_reason"]] += 1

    if args.limit > 0:
        selected = selected[: args.limit]
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) + ["review_selection_reason"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)

    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "input_rows": len(rows),
        "selected_rows": len(selected),
        "criteria": {
            "min_confidence": args.min_confidence,
            "max_confidence": args.max_confidence,
            "emotions": sorted(emotions),
            "sources": sorted(sources),
            "splits": sorted(splits),
            "limit": args.limit,
            "print_rows": args.print_rows,
        },
        "selected_emotion_counts": dict(Counter(clean(row.get("phase1_basic_emotion")) for row in selected)),
        "selected_source_counts": dict(Counter(clean(row.get("youtube_id")) for row in selected)),
        "selected_split_counts": dict(Counter(clean(row.get("split")) for row in selected)),
        "confidence_counts": {
            "below_0_50": sum(float(clean(row.get("phase1_basic_emotion_confidence")) or -1) < 0.50 for row in selected),
            "below_0_60": sum(float(clean(row.get("phase1_basic_emotion_confidence")) or -1) < 0.60 for row in selected),
            "below_0_80": sum(float(clean(row.get("phase1_basic_emotion_confidence")) or -1) < 0.80 for row in selected),
        },
        "selection_reason_counts": dict(reasons),
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.print_rows > 0:
        print(f"\nPretty-printing {min(args.print_rows, len(selected))} selected row(s):")
        display_fields = [
            ("utterance_id", "Utterance ID"),
            ("youtube_id", "Source"),
            ("split", "Split"),
            ("start_time", "Start"),
            ("end_time", "End"),
            ("clip_duration_seconds", "Duration (sec)"),
            ("speaker_role", "Speaker role"),
            ("witness_speaking_status", "Witness speaking"),
            ("phase1_basic_emotion", "Predicted emotion"),
            ("phase1_basic_emotion_confidence", "Confidence"),
            ("review_selection_reason", "Selected because"),
            ("utterance_text", "Transcript"),
            ("clip_video_path", "Video clip"),
            ("clip_audio_path", "Audio clip"),
        ]
        for index, row in enumerate(selected[: args.print_rows], 1):
            print(f"\n--- Row {index} ---")
            for key, label in display_fields:
                value = clean(row.get(key)) or "[blank]"
                if key == "utterance_text":
                    value = shorten(" ".join(value.split()), width=360, placeholder=" ...")
                print(f"{label}: {value}")


if __name__ == "__main__":
    main()
