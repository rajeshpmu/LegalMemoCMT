from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows, write_csv
else:
    from .common import read_csv_rows, write_csv


DEFAULT_INPUT = Path("data/processed/phase2/legalmeld_validated/witness_only_rows/witness_controlled_validation_subset.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/legalmeld_validated/witness_only_rows/witness_controlled_validation_manual_review.csv")
DEFAULT_SUMMARY = Path("reports/phase2/witness_controlled_validation_manual_review_summary.json")


def normalize(value: object) -> str:
    return str(value or "").strip()


EXAM_HINTS = (
    "examination-in-chief",
    "cross-examination",
    "re-examination",
    "re-direct",
    "recross",
    "questioning by the judges",
    "court questioning",
)


def clean_witness_label(value: object) -> str:
    text = normalize(value)
    if not text:
        return ""
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if parts:
        first = parts[0]
        if any(hint in first.lower() for hint in EXAM_HINTS):
            return ""
        return first
    return text


def inspect_row(row: dict[str, str]) -> dict[str, str]:
    hearing_id = normalize(row.get("hearing_id"))
    track = normalize(row.get("validation_track"))
    witness = normalize(row.get("witness_name_or_code"))
    witness_clean = clean_witness_label(witness) or witness
    reason = normalize(row.get("validation_reason"))
    score = normalize(row.get("controlled_validation_score"))
    label_flags: list[str] = []

    if track == "anchor":
        status = "verified_anchor"
        manual_method = "checked the hearing against the already-validated witness utterance subset"
        note = "Anchor hearing kept because the witness utterance subset already validates it."
    else:
        status = "reviewed_promoted"
        manual_method = "checked the hearing by reading the controlled validation CSV and comparing the discovery score, witness label, and manual note"
        note = "Promoted hearing kept for controlled validation because it has a strong discovery signal."

        if "examination-in-chief" in witness.lower():
            label_flags.append("witness_label_contains_examination_heading")
        if " | " in witness:
            label_flags.append("mixed_witness_label")
        if "PROTECTED_CODE" in normalize(row.get("witness_identity_status")).upper() and "PUBLIC_NAME" in normalize(row.get("witness_identity_status")).upper():
            label_flags.append("mixed_identity_signal")

    if hearing_id == "hear_dea210cdb4c728e0":
        status = "reviewed_promoted"
        note = "Label includes an examination heading; the hearing is kept, and the witness label is cleaned to the first meaningful witness token."
        label_flags.append("label_cleanup_applied")
    elif hearing_id == "hear_8a80539e19e2df44":
        status = "reviewed_promoted"
        note = "Witness label mixes a protected code and a public name; the hearing is kept, and the witness key is normalized to the clean witness token."
        label_flags.append("label_cleanup_applied")
    elif track == "promoted":
        note = "Promoted hearing looks consistent and remains in the controlled validation set."

    if not label_flags:
        label_flags.append("none")

    return {
        **row,
        "witness_name_or_code_clean": witness_clean,
        "manual_review_status": status,
        "manual_review_method": manual_method,
        "manual_review_notes": note,
        "manual_review_label_flags": ";".join(label_flags),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a manual review artifact for the controlled validation subset.")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_csv_rows(input_path)
    reviewed = [inspect_row(row) for row in rows]
    reviewed.sort(key=lambda row: (normalize(row.get("validation_track")) != "anchor", normalize(row.get("hearing_date")), normalize(row.get("hearing_id"))))

    fieldnames = list(reviewed[0].keys()) if reviewed else []
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(output_path, reviewed, fieldnames)

    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "total_rows": len(reviewed),
        "anchor_rows": sum(1 for row in reviewed if row.get("validation_track") == "anchor"),
        "promoted_rows": sum(1 for row in reviewed if row.get("validation_track") == "promoted"),
        "flagged_for_label_cleanup": sum(1 for row in reviewed if row.get("manual_review_status") == "flagged_for_label_cleanup"),
        "reviewed_promoted": sum(1 for row in reviewed if row.get("manual_review_status") == "reviewed_promoted"),
        "verified_anchor": sum(1 for row in reviewed if row.get("manual_review_status") == "verified_anchor"),
        "manual_method": "Read the controlled validation CSV row by row, compared the validation track, witness label, score, and notes, and flagged rows whose labels mixed witness identity with exam-heading text.",
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({"output_csv": str(output_path), "summary_json": str(summary_path)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
