from __future__ import annotations

import argparse
from pathlib import Path

from .common import ensure_dir, read_csv_rows, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a tribunal candidate manifest from the Phase 2 case ledger")
    parser.add_argument("--ledger-csv", default="data/phase2/source_manifests/case_candidate_ledger.csv", help="Case candidate ledger CSV")
    parser.add_argument("--output-csv", default="data/phase2/source_manifests/tribunal_manifest_from_ledger.csv", help="Output tribunal manifest CSV")
    parser.add_argument("--include-intri-modal-only", action="store_true", help="Keep only rows marked for tri-modal inclusion")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.ledger_csv))
    out_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=1):
        include_flag = str(row.get("include_in_tri_modal_set") or "").strip().upper()
        if args.include_intri_modal_only and include_flag not in {"YES", "YES_AFTER_LINK_VALIDATION"}:
            continue
        tribunal = (row.get("tribunal") or "").strip()
        case_family = (row.get("case_family") or "").strip()
        case_number = (row.get("case_number") or "").strip()
        out_rows.append(
            {
                "subset_id": f"{tribunal.lower()}_{idx:03d}",
                "tribunal": tribunal,
                "case_family": case_family,
                "case_number": case_number,
                "candidate_priority": (row.get("candidate_priority") or "").strip(),
                "has_video": (row.get("has_video") or "").strip(),
                "tap_count": (row.get("tap_count") or "").strip(),
                "estimated_hours": (row.get("estimated_hours") or "").strip(),
                "estimated_witnesses": (row.get("estimated_witnesses") or "").strip(),
                "source_url": (row.get("source_url") or "").strip(),
                "inventory_search_url": (row.get("inventory_search_url") or "").strip(),
                "curation_action": (row.get("curation_action") or "").strip(),
                "include_in_tri_modal_set": include_flag,
                "notes": (row.get("notes") or "").strip(),
            }
        )

    ensure_dir(Path(args.output_csv).parent)
    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "subset_id",
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
            "notes",
        ],
    )
    print(f"Wrote {len(out_rows)} tribunal candidate rows to {args.output_csv}")


if __name__ == "__main__":
    main()
