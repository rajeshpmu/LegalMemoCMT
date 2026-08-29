"""Pretty-print unresolved and critical-conflict acceptance-gate rows."""
from __future__ import annotations

import argparse
import csv
import textwrap
from pathlib import Path


FIELDS = [
    "utterance_id", "source", "start_time", "end_time", "duration_seconds",
    "speaker_role", "witness_speaking_status", "emotion_target_scope",
    "phase1_basic_emotion", "phase1_basic_emotion_confidence",
    "basic_emotion_review_candidate", "basic_emotion_review_candidate_confidence",
    "proposed_courtroom_affect", "proposed_courtroom_affect_confidence",
    "negative_activation_candidate", "distress_corroboration_present",
    "speaker_emotion_evidence_present", "critical_conflict", "annotation_status",
    "annotation_tier", "final_basic_emotion", "final_courtroom_affect",
    "acceptance_gate_reason", "utterance_text",
]


def value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if row.get(key):
            return row[key].strip()
    return ""


def matches(row: dict[str, str], mode: str) -> bool:
    if mode == "unresolved":
        return row.get("annotation_status", "").upper() == "UNRESOLVED"
    if mode == "critical":
        return row.get("critical_conflict", "").upper() == "YES"
    return (row.get("annotation_status", "").upper() == "UNRESOLVED" or
            row.get("critical_conflict", "").upper() == "YES")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--mode", choices=["unresolved", "critical", "both"], default="both")
    parser.add_argument("--print-rows", type=int, default=0, help="Rows to print; 0 means all selected rows")
    parser.add_argument("--text-width", type=int, default=180)
    parser.add_argument("--output-csv", help="Optional filtered CSV for manual review")
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if matches(row, args.mode)]
    if args.print_rows > 0:
        rows = rows[:args.print_rows]

    if args.output_csv:
        out = Path(args.output_csv); out.parent.mkdir(parents=True, exist_ok=True)
        fields = list(rows[0]) if rows else []
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        print(f"Wrote {len(rows)} filtered rows to {out}")

    print(f"Selected rows: {len(rows)} mode={args.mode}")
    for index, row in enumerate(rows, 1):
        print(f"\n--- Review row {index} ---")
        for field in FIELDS:
            if field == "utterance_text":
                text = value(row, field, "turn_text")
                print(f"{field}: {textwrap.fill(text, width=args.text_width, subsequent_indent='  ')}")
            elif field == "source":
                print(f"{field}: {value(row, 'source', 'youtube_id', 'video_id')}")
            elif field == "duration_seconds":
                print(f"{field}: {value(row, 'duration_seconds', 'clip_duration_seconds', 'duration_sec')}")
            else:
                print(f"{field}: {row.get(field, '')}")


if __name__ == "__main__":
    main()
