from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


def _build_inventory_keys(rows: list[dict[str, str]]) -> tuple[set[str], set[str], set[str]]:
    case_numbers: set[str] = set()
    case_names: set[str] = set()
    for row in rows:
        case_number = _norm(_first(row, "resolved_case_number", "case_number", "requested_case_number"))
        case_name = _norm(_first(row, "case_name", "case_family", "case_description"))
        if case_number:
            case_numbers.add(case_number)
        if case_name:
            case_names.add(case_name)
    return case_numbers, case_names, case_numbers


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare expanded planning rows against the verified inventory.")
    parser.add_argument(
        "--expanded-csv",
        default="data/processed/phase2/phase2_expanded_planning_manifest.csv",
        help="Expanded planning manifest CSV",
    )
    parser.add_argument(
        "--inventory-csv",
        default="data/processed/phase2/verified_case_inventory.csv",
        help="Verified inventory CSV",
    )
    parser.add_argument(
        "--output-csv",
        default="data/processed/phase2/expanded_planning_vs_verified_inventory.csv",
        help="Row-level comparison CSV",
    )
    parser.add_argument(
        "--missing-csv",
        default="data/processed/phase2/expanded_planning_missing_sources.csv",
        help="Subset of expanded rows not covered by the verified inventory",
    )
    parser.add_argument(
        "--summary-json",
        default="reports/phase2/expanded_planning_vs_verified_inventory_summary.json",
        help="Summary JSON for the comparison",
    )
    args = parser.parse_args()

    expanded_rows = read_csv_rows(Path(args.expanded_csv))
    inventory_rows = read_csv_rows(Path(args.inventory_csv))

    inv_case_numbers, inv_case_names, inv_case_number_list = _build_inventory_keys(inventory_rows)

    compared_rows: list[dict[str, str]] = []
    missing_rows: list[dict[str, str]] = []
    covered_count = 0
    missing_count = 0
    category_counts = {
        "already_verified_by_case_number": 0,
        "already_verified_by_case_name": 0,
        "new_expansion_source": 0,
        "unresolved_or_placeholder": 0,
    }

    for idx, row in enumerate(expanded_rows, start=1):
        case_name = _norm(_first(row, "case_name", "case_family"))
        case_number = _norm(_first(row, "resolved_case_number", "case_number"))
        source_id = _first(row, "source_id")
        manifest_kind = _first(row, "manifest_kind")

        if not case_number and not case_name:
            status = "unresolved_or_placeholder"
            reason = "no case number or case name available"
        elif case_number and case_number in inv_case_numbers:
            status = "already_verified_by_case_number"
            reason = "verified inventory already contains this tribunal case number"
        elif case_name and case_name in inv_case_names:
            status = "already_verified_by_case_name"
            reason = "verified inventory already contains this tribunal case name"
        else:
            status = "new_expansion_source"
            reason = "not found in verified inventory"

        if status.startswith("already_verified"):
            covered_count += 1
        else:
            missing_count += 1
            missing_rows.append(
                {
                    **row,
                    "comparison_status": status,
                    "comparison_reason": reason,
                    "expanded_row_number": str(idx),
                }
            )

        category_counts[status] += 1
        compared_rows.append(
            {
                **row,
                "expanded_row_number": str(idx),
                "comparison_status": status,
                "comparison_reason": reason,
                "inventory_case_number_match": "yes" if case_number and case_number in inv_case_numbers else "no",
                "inventory_case_name_match": "yes" if case_name and case_name in inv_case_names else "no",
                "inventory_case_number_found": "yes" if case_number in inv_case_number_list else "no",
                "expanded_source_id": source_id,
                "manifest_kind": manifest_kind,
            }
        )

    output_path = Path(args.output_csv)
    missing_path = Path(args.missing_csv)
    summary_path = Path(args.summary_json)
    ensure_dir(output_path.parent)
    write_csv(
        output_path,
        compared_rows,
        list(compared_rows[0].keys()) if compared_rows else [],
    )
    write_csv(
        missing_path,
        missing_rows,
        list(missing_rows[0].keys()) if missing_rows else [],
    )

    summary = {
        "expanded_csv": str(Path(args.expanded_csv)),
        "inventory_csv": str(Path(args.inventory_csv)),
        "output_csv": str(output_path),
        "missing_csv": str(missing_path),
        "expanded_rows": len(expanded_rows),
        "inventory_rows": len(inventory_rows),
        "covered_rows": covered_count,
        "missing_rows": missing_count,
        "category_counts": category_counts,
        "inventory_case_numbers": sorted(inv_case_number_list),
        "inventory_case_names": sorted(inv_case_names),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
