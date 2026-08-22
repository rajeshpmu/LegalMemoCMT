from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
    from phase2.ucr_case_verification import (
        CaseVerificationResult,
        resolve_case_verification,
        validation_summary,
    )
else:
    from .common import ensure_dir, read_csv_rows, write_csv
    from .ucr_case_verification import CaseVerificationResult, resolve_case_verification, validation_summary


OUTPUT_COLUMNS = [
    "enriched_id",
    "tribunal",
    "case_family",
    "case_number",
    "requested_case_number",
    "resolved_case_number",
    "official_case_page",
    "case_description",
    "case_page_resolved",
    "case_identity_verified",
    "actual_record_count",
    "transcript_record_count",
    "court_recording_count",
    "video_record_count",
    "tap_count",
    "first_record_date",
    "last_record_date",
    "has_transcripts",
    "has_court_recordings",
    "has_videos",
    "verification_status",
    "verification_notes",
    "source_url",
    "notes",
]


def _as_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _summarize_row(row: dict[str, str], resolved: CaseVerificationResult, *, index: int) -> dict[str, object]:
    tribunal = (row.get("tribunal") or "").strip()
    case_family = (row.get("case_family") or "").strip()
    requested_case_number = resolved.requested_case_number
    return {
        "enriched_id": f"{tribunal.lower()}_{index:03d}" if tribunal else f"row_{index:03d}",
        "tribunal": tribunal,
        "case_family": case_family,
        "case_number": requested_case_number,
        "requested_case_number": requested_case_number,
        "resolved_case_number": resolved.resolved_case_number,
        "official_case_page": resolved.official_case_page,
        "case_description": resolved.case_description,
        "case_page_resolved": _as_yes_no(resolved.case_page_resolved),
        "case_identity_verified": _as_yes_no(resolved.case_identity_verified),
        "actual_record_count": resolved.actual_record_count,
        "transcript_record_count": resolved.transcript_record_count,
        "court_recording_count": resolved.court_recording_count,
        "video_record_count": resolved.video_record_count,
        "tap_count": resolved.tap_count,
        "first_record_date": resolved.first_record_date,
        "last_record_date": resolved.last_record_date,
        "has_transcripts": resolved.has_transcripts,
        "has_court_recordings": resolved.has_court_recordings,
        "has_videos": resolved.has_videos,
        "verification_status": resolved.verification_status,
        "verification_notes": resolved.verification_notes,
        "source_url": (row.get("source_url") or "").strip(),
        "notes": (row.get("notes") or "").strip(),
    }


def _control_results() -> list[dict[str, object]]:
    controls = [
        {"kind": "negative", "case_number": "TO_BE_FILLED", "control_url": "/scasedocs/case/TO_BE_FILLED"},
        {"kind": "negative", "case_number": "INVALID-CASE-999", "control_url": "/scasedocs/case/INVALID-CASE-999"},
        {"kind": "negative", "case_number": "ICTR case family", "control_url": "/scasedocs/case/ICTR%20case%20family"},
        {"kind": "positive", "case_number": "IT-95-5/18", "control_url": "/scasedocs/case/IT-95-5%2F18"},
        {"kind": "positive", "case_number": "IT-09-92", "control_url": "/scasedocs/case/IT-09-92"},
        {"kind": "positive", "case_number": "IT-04-81", "control_url": "/scasedocs/case/IT-04-81"},
    ]

    out: list[dict[str, object]] = []
    for control in controls:
        result = resolve_case_verification(control["case_number"])
        summary = validation_summary(result)
        summary.update(
            {
                "control_kind": control["kind"],
                "control_url": control["control_url"],
                "pass": False,
            }
        )
        if control["kind"] == "positive":
            summary["pass"] = bool(result.case_identity_verified and result.actual_record_count > 0)
        else:
            summary["pass"] = bool(result.actual_record_count == 0 and result.has_videos != "yes")
        out.append(summary)
    return out


def _ledger_summary(rows: list[dict[str, object]]) -> dict[str, int]:
    verified = sum(1 for row in rows if str(row.get("verification_status") or "").strip().lower() == "verified")
    unresolved = sum(1 for row in rows if str(row.get("verification_status") or "").strip().lower() == "unresolved")
    invalid = sum(1 for row in rows if str(row.get("verification_status") or "").strip().lower() == "invalid_case_number")
    return {
        "verified_cases": verified,
        "unresolved_cases": unresolved,
        "invalid_case_rows": invalid,
    }


def _build_validation_report(rows: list[dict[str, object]]) -> dict[str, object]:
    control_results = _control_results()
    positive_controls = [row for row in control_results if row["control_kind"] == "positive"]
    negative_controls = [row for row in control_results if row["control_kind"] == "negative"]

    false_positive_count = sum(
        1
        for row in negative_controls
        if row["actual_record_count"] > 0 or row["has_videos"] == "yes" or row["verification_status"] == "verified"
    )

    ledger_summary = _ledger_summary(rows)
    return {
        "positive_controls_tested": len(positive_controls),
        "negative_controls_tested": len(negative_controls),
        "positive_controls_passed": sum(1 for row in positive_controls if row["pass"]),
        "negative_controls_passed": sum(1 for row in negative_controls if row["pass"]),
        "false_positive_count": false_positive_count,
        **ledger_summary,
        "control_results": control_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the Phase 2 case ledger against live UCR JSON APIs")
    parser.add_argument("--ledger-csv", default="data/phase2/source_manifests/case_candidate_ledger.csv", help="Primary input case ledger CSV")
    parser.add_argument(
        "--extra-ledger-csv",
        action="append",
        default=[],
        help="Additional ledger CSVs to append before verification; may be repeated",
    )
    parser.add_argument(
        "--output-csv",
        default="data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv",
        help="Output verified ledger CSV",
    )
    parser.add_argument(
        "--validation-json",
        default="reports/phase2/ucr_enrichment_validation.json",
        help="Output validation report JSON",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit")
    args = parser.parse_args()

    input_paths = [Path(args.ledger_csv), *[Path(p) for p in args.extra_ledger_csv]]
    rows: list[dict[str, str]] = []
    for path in input_paths:
        rows.extend(read_csv_rows(path))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    out_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=1):
        requested_case_number = row.get("case_number") or row.get("case_family") or ""
        resolved = resolve_case_verification(requested_case_number)
        out_rows.append(_summarize_row(row, resolved, index=idx))
        print(
            f"row={idx} case_family={row.get('case_family', '').strip()!r} "
            f"case_number={resolved.requested_case_number or '(none)'} "
            f"status={resolved.verification_status} records={resolved.actual_record_count}"
        )

    ensure_dir(Path(args.output_csv).parent)
    write_csv(Path(args.output_csv), out_rows, OUTPUT_COLUMNS)
    print(f"Wrote {len(out_rows)} verified ledger rows to {args.output_csv}")

    validation_report = _build_validation_report(out_rows)
    validation_path = Path(args.validation_json)
    ensure_dir(validation_path.parent)
    validation_path.write_text(json.dumps(validation_report, indent=2), encoding="utf-8")
    print(f"Wrote UCR enrichment validation report to {validation_path}")


if __name__ == "__main__":
    main()
