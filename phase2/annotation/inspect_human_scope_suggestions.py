"""Print targeted human-review rows from scope suggestions."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from textwrap import shorten


def clean(row: dict, key: str) -> str:
    return str(row.get(key, "")).strip() or "[blank]"


def number(row: dict, key: str, default: float = 1.0) -> float:
    try:
        return float(row.get(key, "") or default)
    except (TypeError, ValueError):
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument(
        "--target",
        action="append",
        choices=[
            "NO_EMOTION_CONTENT",
            "OTHER_PERSON_DESCRIBED",
            "QUOTED_SPEECH",
            "EVENT_DESCRIBED",
            "SELF_EXPRESSED",
            "UNCLEAR",
        ],
        help="Filter by auto-review target; repeat for multiple targets.",
    )
    parser.add_argument("--low-confidence", action="store_true")
    parser.add_argument("--disagreement", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output-csv")
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    targets = set(args.target or [])

    def selected(row: dict) -> bool:
        if targets and clean(row, "auto_review_target_scope") not in targets:
            return False
        if args.low_confidence and clean(row, "deberta_target_scope_confidence") != "[blank]":
            if number(row, "deberta_target_scope_confidence") >= 0.60 and number(row, "deberta_target_margin") >= 0.10:
                return False
        if args.disagreement and clean(row, "target_scope_disagreement") != "YES":
            return False
        return True

    selected_rows = [row for row in rows if selected(row)]
    if args.output_csv:
        output = Path(args.output_csv)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
            writer.writeheader()
            writer.writerows(selected_rows)

    print(f"rows selected={len(selected_rows)} showing={min(args.limit, len(selected_rows))}")
    fields = [
        ("utterance_id", "Utterance ID"),
        ("start_time", "Start"),
        ("end_time", "End"),
        ("speaker_role", "Role"),
        ("utterance_text", "Transcript"),
        ("emotion_target_scope", "Original target scope"),
        ("auto_review_target_scope", "Suggested target scope"),
        ("auto_review_temporal_scope", "Suggested temporal scope"),
        ("auto_review_confidence", "Suggestion confidence"),
        ("deberta_target_scope", "DeBERTa target"),
        ("deberta_target_scope_confidence", "DeBERTa target confidence"),
        ("deberta_target_margin", "DeBERTa target margin"),
        ("deberta_temporal_scope", "DeBERTa temporal"),
        ("deberta_temporal_scope_confidence", "DeBERTa temporal confidence"),
        ("target_scope_disagreement", "Target disagreement"),
        ("auto_review_reason", "Suggestion reason"),
    ]
    for index, row in enumerate(selected_rows[: args.limit], 1):
        print(f"\n--- Row {index} ---")
        for key, label in fields:
            value = clean(row, key)
            if key == "utterance_text":
                value = shorten(" ".join(value.split()), width=900, placeholder=" ...")
            print(f"{label}: {value}")


if __name__ == "__main__":
    main()
