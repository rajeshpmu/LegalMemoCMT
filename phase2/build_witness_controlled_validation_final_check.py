from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows
else:
    from .common import read_csv_rows


DEFAULT_INPUT = Path(
    "data/processed/phase2/legalmeld_validated/witness_only_rows/witness_controlled_validation_manual_review.csv"
)
DEFAULT_SUMMARY = Path("reports/phase2/witness_controlled_validation_final_check_summary.json")


def normalize(value: object) -> str:
    return str(value or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the final consistency check on the controlled validation witness subset."
    )
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_csv_rows(input_path)

    tracks = Counter(normalize(row.get("validation_track")) for row in rows)
    statuses = Counter(normalize(row.get("manual_review_status")) for row in rows)
    clean_labels = sum(1 for row in rows if normalize(row.get("witness_name_or_code_clean")))
    mixed_labels = sum(
        1
        for row in rows
        if "|" in normalize(row.get("witness_name_or_code"))
        or "examination-in-chief" in normalize(row.get("witness_name_or_code")).lower()
    )
    anchor_rows = sum(1 for row in rows if normalize(row.get("validation_track")) == "anchor")
    promoted_rows = sum(1 for row in rows if normalize(row.get("validation_track")) == "promoted")
    cleanup_rows = sum(1 for row in rows if "label_cleanup_applied" in normalize(row.get("manual_review_label_flags")))
    unresolved_cleanup_rows = sum(
        1
        for row in rows
        if normalize(row.get("manual_review_label_flags")) != "none"
        and "label_cleanup_applied" not in normalize(row.get("manual_review_label_flags"))
    )
    verified_anchor_rows = sum(1 for row in rows if normalize(row.get("manual_review_status")) == "verified_anchor")
    reviewed_promoted_rows = sum(1 for row in rows if normalize(row.get("manual_review_status")) == "reviewed_promoted")

    issues: list[str] = []
    if len(rows) != 10:
        issues.append(f"expected 10 rows but found {len(rows)}")
    if anchor_rows != 4:
        issues.append(f"expected 4 anchor rows but found {anchor_rows}")
    if promoted_rows != 6:
        issues.append(f"expected 6 promoted rows but found {promoted_rows}")
    if verified_anchor_rows != 4:
        issues.append(f"expected 4 verified_anchor rows but found {verified_anchor_rows}")
    if reviewed_promoted_rows != 6:
        issues.append(f"expected 6 reviewed_promoted rows but found {reviewed_promoted_rows}")
    if unresolved_cleanup_rows != 0:
        issues.append(
            f"expected 0 unresolved label-cleanup rows but found {unresolved_cleanup_rows}"
        )
    if clean_labels != len(rows):
        issues.append(f"expected all rows to have a cleaned witness label but only {clean_labels} do")

    summary = {
        "input_csv": str(input_path),
        "total_rows": len(rows),
        "anchor_rows": anchor_rows,
        "promoted_rows": promoted_rows,
        "verified_anchor_rows": verified_anchor_rows,
        "reviewed_promoted_rows": reviewed_promoted_rows,
        "label_cleanup_rows": cleanup_rows,
        "unresolved_label_cleanup_rows": unresolved_cleanup_rows,
        "clean_witness_labels": clean_labels,
        "mixed_label_candidates": mixed_labels,
        "validation_track_counts": dict(tracks),
        "manual_review_status_counts": dict(statuses),
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "manual_method": (
            "Read the controlled validation manual-review artifact row by row and checked whether the subset still had "
            "the expected 4 anchor rows, 6 promoted rows, cleaned witness labels, and no remaining cleanup flags."
        ),
    }

    output_path = Path(args.summary_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
