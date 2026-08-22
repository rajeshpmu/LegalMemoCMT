from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


DEFAULT_BASE_MANIFEST = Path("data/phase2/source_manifests/tribunal_sources_target_dataset.csv")
DEFAULT_REVIEW_CSV = Path("data/processed/phase2/tribunal_source_broadening_review.csv")
DEFAULT_VERIFIED_ADDITIONS_CSV = Path("data/phase2/source_manifests/verified_tap_case_additions.csv")
DEFAULT_OUTPUT = Path("data/phase2/source_manifests/tribunal_sources_target_dataset_broadened.csv")


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _slug(text: str) -> str:
    import re

    text = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return text or "item"


def _copy_row(row: dict[str, str]) -> dict[str, str]:
    return {k: ("" if v is None else str(v)) for k, v in row.items()}


def _derive_subset_id(row: dict[str, str], existing_ids: set[str]) -> str:
    tribunal = _slug(row.get("tribunal", "tribunal"))
    family = _slug(row.get("case_family", row.get("case_name", "case")))
    base = f"{tribunal}_{family}"
    idx = 1
    candidate = f"{base}_{idx:02d}"
    while candidate in existing_ids:
        idx += 1
        candidate = f"{base}_{idx:02d}"
    existing_ids.add(candidate)
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a broadened tribunal source manifest from reviewed candidate rows.")
    parser.add_argument("--base-manifest", default=str(DEFAULT_BASE_MANIFEST), help="Current tribunal source manifest")
    parser.add_argument("--review-csv", default=str(DEFAULT_REVIEW_CSV), help="Ranked review CSV with manual_selection flags")
    parser.add_argument(
        "--verified-additions-csv",
        default=str(DEFAULT_VERIFIED_ADDITIONS_CSV),
        help="Optional CSV of already-verified TAP-bearing case additions to always include in the broadened manifest.",
    )
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT), help="Broadened tribunal source manifest")
    parser.add_argument(
        "--selection-column",
        default="manual_selection",
        help="Column set to YES to include a review row in the broadened manifest",
    )
    parser.add_argument(
        "--selection-values",
        default="YES,SELECTED,TRUE,1",
        help="Comma-separated values that count as selected",
    )
    parser.add_argument(
        "--include-hold-for-link-validation",
        action="store_true",
        help="Also include rows marked hold_for_link_validation, which are source-level candidates that are not yet TAP-verified.",
    )
    args = parser.parse_args()

    base_rows = read_csv_rows(Path(args.base_manifest))
    review_rows = read_csv_rows(Path(args.review_csv))
    verified_additions_rows = read_csv_rows(Path(args.verified_additions_csv)) if Path(args.verified_additions_csv).exists() else []
    selected_values = {_norm(item) for item in args.selection_values.split(",") if _norm(item)}

    existing_subset_ids = {str(row.get("subset_id") or "").strip() for row in base_rows if str(row.get("subset_id") or "").strip()}
    existing_families = {_norm(row.get("case_family")) for row in base_rows if _norm(row.get("case_family"))}
    existing_case_numbers = {_norm(row.get("case_number")) for row in base_rows if _norm(row.get("case_number"))}

    for row in verified_additions_rows:
        case_family = _norm(row.get("case_family"))
        case_number = _norm(row.get("case_number"))
        if case_family in existing_families or case_number in existing_case_numbers:
            continue
        subset_id = str(row.get("subset_id") or "").strip() or _derive_subset_id(row, existing_subset_ids)
        derived = {
            "subset_id": subset_id,
            "tribunal": str(row.get("tribunal") or "").strip(),
            "case_family": str(row.get("case_family") or "").strip(),
            "content_type": str(row.get("content_type") or "").strip() or "Witness testimony",
            "source_url": str(row.get("source_url") or "").strip() or "https://ucr.irmct.org/",
            "target_video_hours": str(row.get("target_video_hours") or row.get("estimated_hours") or "").strip() or "10",
            "target_witnesses": str(row.get("target_witnesses") or row.get("estimated_witnesses") or "").strip() or "4",
            "notes": f"Verified TAP-bearing addition; {str(row.get('notes') or '').strip()}",
        }
        base_rows.append(derived)
        existing_subset_ids.add(subset_id)
        existing_families.add(case_family)
        existing_case_numbers.add(case_number)

    new_rows: list[dict[str, str]] = []
    added: list[dict[str, str]] = []
    for row in review_rows:
        selection_value = _norm(row.get(args.selection_column))
        recommended_action = _norm(row.get("recommended_action"))
        selected = selection_value in selected_values or (not selection_value and recommended_action == "broaden_now")
        if not selected and recommended_action == "broaden_now":
            selected = True
        if not selected and args.include_hold_for_link_validation and recommended_action == "hold_for_link_validation":
            selected = True
        if not selected:
            continue
        case_family = _norm(row.get("case_family"))
        case_number = _norm(row.get("case_number"))
        if case_family in existing_families or case_number in existing_case_numbers:
            continue
        subset_id = _derive_subset_id(row, existing_subset_ids)
        content_type = str(row.get("content_type") or "").strip() or "Witness testimony"
        derived = {
            "subset_id": subset_id,
            "tribunal": str(row.get("tribunal") or "").strip(),
            "case_family": str(row.get("case_family") or "").strip(),
            "content_type": content_type,
            "source_url": str(row.get("source_url") or "").strip() or "https://ucr.irmct.org/",
            "target_video_hours": str(row.get("estimated_hours") or "").strip() or "10",
            "target_witnesses": str(row.get("estimated_witnesses") or "").strip() or "4",
            "notes": f"Broadened from {Path(args.review_csv).name}; {str(row.get('notes') or '').strip()}",
        }
        new_rows.append(derived)
        added.append(derived)

    combined = [*base_rows, *new_rows]
    ensure_dir(Path(args.output_csv).parent)
    write_csv(
        Path(args.output_csv),
        combined,
        ["subset_id", "tribunal", "case_family", "content_type", "source_url", "target_video_hours", "target_witnesses", "notes"],
    )

    print(
        {
            "base_rows": len(base_rows),
            "review_rows": len(review_rows),
            "added_rows": len(added),
            "output_csv": str(Path(args.output_csv)),
            "added_case_families": [row["case_family"] for row in added],
        }
    )


if __name__ == "__main__":
    main()
