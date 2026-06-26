from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


def _slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return text or "item"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a witness candidate manifest from the Phase 2 case ledger")
    parser.add_argument("--ledger-csv", default="data/phase2/source_manifests/case_candidate_ledger.csv", help="Case candidate ledger CSV")
    parser.add_argument("--output-csv", default="data/phase2/source_manifests/witness_manifest_from_ledger.csv", help="Output witness manifest CSV")
    parser.add_argument("--only-video-cases", action="store_true", help="Keep only rows flagged for tri-modal inclusion")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.ledger_csv))
    out_rows: list[dict[str, object]] = []

    for idx, row in enumerate(rows, start=1):
        include_flag = str(row.get("include_in_tri_modal_set") or "").strip().upper()
        if args.only_video_cases and include_flag not in {"YES", "YES_AFTER_LINK_VALIDATION"}:
            continue

        tribunal = (row.get("tribunal") or "").strip()
        case_family = (row.get("case_family") or "").strip()
        case_number = (row.get("case_number") or "").strip()
        estimated_witnesses = (row.get("estimated_witnesses") or "").strip()
        estimated_hours = (row.get("estimated_hours") or "").strip()

        out_rows.append(
            {
                "tribunal": tribunal,
                "case_name": case_family,
                "hearing_date": "",
                "witness_name": f"{case_family} witness candidate {idx}",
                "witness_type": "Witness",
                "transcript_url": (row.get("source_url") or "").strip(),
                "video_url": (row.get("inventory_search_url") or "").strip(),
                "duration_minutes": "",
                "speaker_role": "Witness",
                "download_status": "Pending",
                "annotation_status": "Not Started",
                "utterance_count": "",
                "emotion_label_status": "Pending",
                "credibility_label_status": "Pending",
                "notes": (
                    f"Ledger-based witness candidate from {case_number}; "
                    f"estimated_witnesses={estimated_witnesses}; estimated_hours={estimated_hours}; "
                    f"curation_action={row.get('curation_action', '')}"
                ),
                "manifest_id": f"{_slug(tribunal)}_{_slug(case_family)}_{idx:03d}",
            }
        )

    ensure_dir(Path(args.output_csv).parent)
    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "manifest_id",
            "tribunal",
            "case_name",
            "hearing_date",
            "witness_name",
            "witness_type",
            "transcript_url",
            "video_url",
            "duration_minutes",
            "speaker_role",
            "download_status",
            "annotation_status",
            "utterance_count",
            "emotion_label_status",
            "credibility_label_status",
            "notes",
        ],
    )
    print(f"Wrote {len(out_rows)} witness candidate rows to {args.output_csv}")


if __name__ == "__main__":
    main()
