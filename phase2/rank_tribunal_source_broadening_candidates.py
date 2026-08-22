from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


DEFAULT_LEDGER = Path("data/phase2/source_manifests/case_candidate_ledger.csv")
DEFAULT_SOURCE_MANIFEST = Path("data/phase2/source_manifests/tribunal_sources_target_dataset.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/tribunal_source_broadening_review.csv")
DEFAULT_SUMMARY = Path("reports/phase2/tribunal_source_broadening_review_summary.json")


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _as_int(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    match = "".join(ch for ch in text if ch.isdigit())
    try:
        return int(match) if match else 0
    except Exception:
        return 0


def _priority_rank(value: str) -> int:
    value = _norm(value)
    if value.startswith("high"):
        return 3
    if value.startswith("med"):
        return 2
    if value.startswith("low"):
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank tribunal-source broadening candidates from the case ledger.")
    parser.add_argument("--ledger-csv", default=str(DEFAULT_LEDGER), help="Case candidate ledger")
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST), help="Current tribunal source manifest")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT), help="Ranked review output")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY), help="Summary JSON for the review")
    args = parser.parse_args()

    ledger_rows = read_csv_rows(Path(args.ledger_csv))
    source_rows = read_csv_rows(Path(args.source_manifest))

    source_case_families = {_norm(row.get("case_family")) for row in source_rows if _norm(row.get("case_family"))}
    source_case_numbers = {_norm(row.get("case_number")) for row in source_rows if _norm(row.get("case_number"))}

    review_rows: list[dict[str, str]] = []
    for row in ledger_rows:
        case_family = str(row.get("case_family") or "").strip()
        case_number = str(row.get("case_number") or "").strip()
        tribunal = str(row.get("tribunal") or "").strip()
        if not case_family:
            continue
        in_source_manifest = _norm(case_family) in source_case_families or _norm(case_number) in source_case_numbers
        if in_source_manifest:
            continue

        candidate_priority = str(row.get("candidate_priority") or "").strip()
        has_video = str(row.get("has_video") or "").strip()
        include_flag = str(row.get("include_in_tri_modal_set") or "").strip()
        curation_action = str(row.get("curation_action") or "").strip()
        tap_count = str(row.get("tap_count") or "").strip()
        estimated_hours = str(row.get("estimated_hours") or "").strip()
        estimated_witnesses = str(row.get("estimated_witnesses") or "").strip()
        source_url = str(row.get("source_url") or "").strip()
        inventory_search_url = str(row.get("inventory_search_url") or "").strip()
        notes = str(row.get("notes") or "").strip()

        if include_flag.upper() == "YES_AFTER_LINK_VALIDATION" or curation_action.upper().startswith("YES_AFTER_LINK_VALIDATION"):
            recommended_action = "broaden_now"
        elif "ONLY_IF_VIDEO_LINKS_RESOLVED" in include_flag.upper() or "ONLY_IF_VIDEO_LINKS_RESOLVED" in curation_action.upper():
            recommended_action = "hold_for_link_validation"
        else:
            recommended_action = "manual_review"

        score = _priority_rank(candidate_priority) * 100
        score += 25 if "yes" in _norm(has_video) else 0
        score += 10 if recommended_action == "broaden_now" else 0
        score += min(_as_int(tap_count), 50)

        review_rows.append(
            {
                "tribunal": tribunal,
                "case_family": case_family,
                "case_number": case_number,
                "candidate_priority": candidate_priority,
                "has_video": has_video,
                "tap_count": tap_count,
                "estimated_hours": estimated_hours,
                "estimated_witnesses": estimated_witnesses,
                "source_url": source_url,
                "inventory_search_url": inventory_search_url,
                "curation_action": curation_action,
                "include_in_tri_modal_set": include_flag,
                "recommended_action": recommended_action,
                "recommended_score": str(score),
                "notes": notes,
                "manual_selection": "NO",
            }
        )

    review_rows.sort(
        key=lambda row: (
            -int(row.get("recommended_score") or 0),
            _norm(row.get("tribunal")),
            _norm(row.get("case_family")),
        )
    )

    output_path = Path(args.output_csv)
    ensure_dir(output_path.parent)
    write_csv(
        output_path,
        review_rows,
        [
            "tribunal",
            "case_family",
            "case_number",
            "candidate_priority",
            "has_video",
            "tap_count",
            "estimated_hours",
            "estimated_witnesses",
            "source_url",
            "inventory_search_url",
            "curation_action",
            "include_in_tri_modal_set",
            "recommended_action",
            "recommended_score",
            "notes",
            "manual_selection",
        ],
    )

    summary = {
        "ledger_csv": str(Path(args.ledger_csv)),
        "source_manifest": str(Path(args.source_manifest)),
        "output_csv": str(output_path),
        "ledger_rows": len(ledger_rows),
        "source_manifest_rows": len(source_rows),
        "review_rows": len(review_rows),
        "recommended_broaden_now": sum(1 for row in review_rows if row["recommended_action"] == "broaden_now"),
        "recommended_hold": sum(1 for row in review_rows if row["recommended_action"] == "hold_for_link_validation"),
        "recommended_manual_review": sum(1 for row in review_rows if row["recommended_action"] == "manual_review"),
        "new_case_families": [row["case_family"] for row in review_rows],
    }
    summary_path = Path(args.summary_json)
    ensure_dir(summary_path.parent)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
