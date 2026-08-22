from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.filter_legalmeld_rows_by_use import classify_row, reason_for_row
else:
    from .filter_legalmeld_rows_by_use import classify_row, reason_for_row


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def usable_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        categories = classify_row(row)
        if "usable" in categories:
            item = dict(row)
            item["training_use_categories"] = ";".join(categories)
            item["training_use_reason"] = reason_for_row(row, categories)
            out[str(row.get("utterance_id") or "")] = item
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare usable rows for a hearing across two exports.")
    parser.add_argument("--old-csv", required=True)
    parser.add_argument("--new-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--hearing-id", required=True)
    args = parser.parse_args()

    old_rows = [row for row in load_rows(Path(args.old_csv)) if row.get("hearing_id") == args.hearing_id]
    new_rows = [row for row in load_rows(Path(args.new_csv)) if row.get("hearing_id") == args.hearing_id]
    old_usable = usable_rows(old_rows)
    new_usable = usable_rows(new_rows)

    all_ids = sorted(set(old_usable) | set(new_usable))
    fieldnames = [
        "utterance_id",
        "status",
        "old_alignment_confidence",
        "old_quality_tier",
        "old_split",
        "old_alignment_status",
        "old_start_time",
        "old_end_time",
        "old_utterance_text",
        "old_reason",
        "new_alignment_confidence",
        "new_quality_tier",
        "new_split",
        "new_alignment_status",
        "new_start_time",
        "new_end_time",
        "new_utterance_text",
        "new_reason",
    ]

    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for uid in all_ids:
            old = old_usable.get(uid)
            new = new_usable.get(uid)
            status = "same" if old and new else "only_old" if old else "only_new"
            writer.writerow(
                {
                    "utterance_id": uid,
                    "status": status,
                    "old_alignment_confidence": old.get("alignment_confidence", "") if old else "",
                    "old_quality_tier": old.get("quality_tier", "") if old else "",
                    "old_split": old.get("split", "") if old else "",
                    "old_alignment_status": old.get("alignment_status", "") if old else "",
                    "old_start_time": old.get("start_time", "") if old else "",
                    "old_end_time": old.get("end_time", "") if old else "",
                    "old_utterance_text": old.get("utterance_text", "") if old else "",
                    "old_reason": old.get("training_use_reason", "") if old else "",
                    "new_alignment_confidence": new.get("alignment_confidence", "") if new else "",
                    "new_quality_tier": new.get("quality_tier", "") if new else "",
                    "new_split": new.get("split", "") if new else "",
                    "new_alignment_status": new.get("alignment_status", "") if new else "",
                    "new_start_time": new.get("start_time", "") if new else "",
                    "new_end_time": new.get("end_time", "") if new else "",
                    "new_utterance_text": new.get("utterance_text", "") if new else "",
                    "new_reason": new.get("training_use_reason", "") if new else "",
                }
            )

    print(
        {
            "hearing_id": args.hearing_id,
            "old_usable": len(old_usable),
            "new_usable": len(new_usable),
            "output_csv": str(out_path),
        }
    )


if __name__ == "__main__":
    main()
