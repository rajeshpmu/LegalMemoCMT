"""Finalize a documented bulk decision for the Clancy emotion-review queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-csv", required=True, help="Reviewer copy created by the review-manifest builder")
    parser.add_argument("--machine-csv", required=True, help="The 1,010-row machine-promoted manifest")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--reviewer", required=True, help="Reviewer name or identifier")
    parser.add_argument("--notes", default="Bulk-confirmed after manual review of machine-promoted rows")
    parser.add_argument(
        "--confirm-machine-promoted",
        action="store_true",
        help="Required safety flag: confirm the stated bulk-review decision",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.confirm_machine_promoted:
        raise SystemExit("Refusing to finalize: add --confirm-machine-promoted after verifying the 1,010 rows")

    output = Path(args.output_csv)
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite existing reviewer file: {output}; use --overwrite intentionally")

    review = pd.read_csv(args.review_csv, dtype=str).fillna("")
    machine = pd.read_csv(args.machine_csv, dtype=str).fillna("")
    for name, frame in (("review", review), ("machine", machine)):
        if "utterance_id" not in frame.columns:
            raise SystemExit(f"{name} CSV requires utterance_id")
        if frame["utterance_id"].duplicated().any():
            raise SystemExit(f"{name} CSV contains duplicate utterance_id values")
    if "final_training_basic_emotion" not in machine.columns:
        raise SystemExit("Machine CSV requires final_training_basic_emotion")

    promoted = machine.set_index("utterance_id")
    promoted_ids = set(promoted.index)
    review_ids = set(review["utterance_id"])
    missing_promoted = sorted(promoted_ids - review_ids)
    if missing_promoted:
        raise SystemExit(
            f"Reviewer CSV is missing {len(missing_promoted)} machine-promoted IDs; rebuild the reviewer copy first"
        )

    out = review.copy()
    if "human_basic_emotion" not in out:
        out["human_basic_emotion"] = ""
    if "human_basic_emotion_review_status" not in out:
        out["human_basic_emotion_review_status"] = "UNREVIEWED"
    for column in (
        "human_basic_emotion_confidence",
        "human_basic_emotion_reviewer",
        "human_basic_emotion_notes",
    ):
        if column not in out:
            out[column] = ""

    confirmed = 0
    deferred = 0
    for index, row in out.iterrows():
        uid = row["utterance_id"]
        if uid in promoted_ids:
            label = str(promoted.at[uid, "final_training_basic_emotion"]).strip()
            if not label or label == "UNRESOLVED":
                raise SystemExit(f"Machine-promoted row has no usable final label: {uid}")
            out.at[index, "human_basic_emotion"] = label
            out.at[index, "human_basic_emotion_review_status"] = "CONFIRMED"
            out.at[index, "human_basic_emotion_reviewer"] = args.reviewer
            out.at[index, "human_basic_emotion_notes"] = args.notes
            confirmed += 1
        else:
            out.at[index, "human_basic_emotion"] = ""
            out.at[index, "human_basic_emotion_review_status"] = "DEFERRED"
            out.at[index, "human_basic_emotion_reviewer"] = args.reviewer
            out.at[index, "human_basic_emotion_notes"] = "Not in machine-promoted set; deferred for later review"
            deferred += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    summary = {
        "review_csv": args.review_csv,
        "machine_csv": args.machine_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(out),
        "confirmed_machine_promoted_rows": confirmed,
        "deferred_remaining_rows": deferred,
        "reviewer": args.reviewer,
        "notes": [
            "CONFIRMED rows inherit final_training_basic_emotion from the machine manifest after the stated manual review.",
            "DEFERRED rows have no human_basic_emotion label and are excluded by the human-gold merge.",
            "This bulk operation records a reviewer decision; it is not independent multi-reviewer adjudication.",
            "Machine fields and provenance remain preserved in the reviewer output.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
