from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, sha1_short, write_csv
    from phase2.ucr_case_verification import (
        resolve_case_verification,
        normalize_case_number,
        normalize_document_path,
    )
else:
    from .common import ensure_dir, read_csv_rows, sha1_short, write_csv
    from .ucr_case_verification import resolve_case_verification, normalize_case_number, normalize_document_path


OUTPUT_COLUMNS = [
    "inventory_id",
    "source_record_id",
    "requested_case_number",
    "resolved_case_number",
    "case_name",
    "case_number",
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
    "document_title",
    "document_type",
    "doc_signature_date",
    "doc_source_desc",
    "document_path",
    "is_video",
    "source_status",
    "verification_status",
    "record_case_number",
    "index_management_id",
    "document_id",
    "record_id",
    "source_endpoint",
    "verification_notes",
]


def _as_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _source_key(row: dict[str, str], index: int) -> str:
    for candidate in ("enriched_id", "subset_id", "manifest_id", "source_record_id", "record_id"):
        value = (row.get(candidate) or "").strip()
        if value:
            return value
    case_number = normalize_case_number(row.get("resolved_case_number") or row.get("case_number") or row.get("case_family") or "")
    return case_number or f"record_{index}"


def _eligible_rows(rows: list[dict[str, str]], *, include_unverified: bool) -> list[dict[str, str]]:
    has_verification_columns = any(
        "verification_status" in row or "case_identity_verified" in row or "resolved_case_number" in row for row in rows
    )
    if include_unverified or not has_verification_columns:
        return rows

    eligible: list[dict[str, str]] = []
    for row in rows:
        status = (row.get("verification_status") or "").strip().lower()
        verified_flag = (row.get("case_identity_verified") or "").strip().lower()
        if status == "verified" or verified_flag in {"yes", "true", "1"}:
            eligible.append(row)
    return eligible


def _record_identity_key(record: dict[str, object]) -> str:
    for candidate in ("IndexManagementId", "DocumentId", "RecordID"):
        value = str(record.get(candidate) or "").strip()
        if value:
            return value
    return sha1_short(
        "|".join(
            [
                str(record.get("resolved_case_number") or ""),
                str(record.get("record_case_number") or ""),
                str(record.get("DocumentTitle") or ""),
                str(record.get("DocSignatureDate") or ""),
                str(record.get("DocumentPath") or ""),
            ]
        ),
        length=16,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a verified UCR case inventory from the Phase 2 case ledger")
    parser.add_argument(
        "--source-csv",
        default="data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv",
        help="Verified case ledger CSV",
    )
    parser.add_argument("--output-csv", default="data/processed/phase2/verified_case_inventory.csv", help="Output verified inventory CSV")
    parser.add_argument("--include-unverified", action="store_true", help="Keep rows even if the source ledger is not verified")
    parser.add_argument("--limit", type=int, default=0, help="Optional input row limit")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    eligible_rows = _eligible_rows(rows, include_unverified=args.include_unverified)
    processed_cases: set[str] = set()
    out_rows: list[dict[str, object]] = []

    for idx, row in enumerate(eligible_rows, start=1):
        requested_case_number = normalize_case_number(row.get("case_number") or row.get("requested_case_number") or row.get("case_family") or "")
        source_key = _source_key(row, idx)
        resolved_case_number = normalize_case_number(row.get("resolved_case_number") or requested_case_number)
        if not resolved_case_number:
            resolved_case_number = requested_case_number

        if resolved_case_number in processed_cases:
            continue

        verification = resolve_case_verification(requested_case_number)
        if verification.verification_status != "verified" or not verification.records:
            print(
                f"skip source={source_key!r} case={requested_case_number or '(none)'} "
                f"status={verification.verification_status}"
            )
            continue

        processed_cases.add(verification.resolved_case_number or requested_case_number)
        case_name = (row.get("case_family") or verification.case_description or "").strip()
        for record_index, record in enumerate(verification.records, start=1):
            record_case_number = normalize_case_number(record.get("record_case_number") or record.get("CaseNumber") or "")
            doc_path = normalize_document_path(record.get("DocumentPath") or "")
            record_key = _record_identity_key(record)
            inventory_key = sha1_short(
                "|".join([source_key, verification.resolved_case_number, record_key, str(record_index)]),
                length=12,
            )
            out_rows.append(
                {
                    "inventory_id": f"{source_key}_{record_index}_{inventory_key}",
                    "source_record_id": source_key,
                    "requested_case_number": requested_case_number,
                    "resolved_case_number": verification.resolved_case_number,
                    "case_name": case_name,
                    "case_number": verification.resolved_case_number,
                    "case_description": verification.case_description,
                    "case_page_resolved": _as_yes_no(verification.case_page_resolved),
                    "case_identity_verified": _as_yes_no(verification.case_identity_verified),
                    "actual_record_count": verification.actual_record_count,
                    "transcript_record_count": verification.transcript_record_count,
                    "court_recording_count": verification.court_recording_count,
                    "video_record_count": verification.video_record_count,
                    "tap_count": verification.tap_count,
                    "first_record_date": verification.first_record_date,
                    "last_record_date": verification.last_record_date,
                    "document_title": record.get("DocumentTitle") or "",
                    "document_type": record.get("DocumentType") or "",
                    "doc_signature_date": record.get("DocSignatureDate") or "",
                    "doc_source_desc": record.get("DocSourceDesc") or "",
                    "document_path": doc_path,
                    "is_video": _as_yes_no(str(record.get("DocumentType") or "").strip().upper() == "TAP" or Path(doc_path).suffix.lower() in {".mp4", ".webm", ".mov", ".mkv", ".m4v"}),
                    "source_status": verification.verification_status,
                    "verification_status": verification.verification_status,
                    "record_case_number": record_case_number,
                    "index_management_id": record.get("IndexManagementId") or "",
                    "document_id": record.get("DocumentId") or "",
                    "record_id": record.get("RecordID") or "",
                    "source_endpoint": record.get("source_endpoint") or "",
                    "verification_notes": verification.verification_notes,
                }
            )

        print(
            f"case={verification.resolved_case_number or requested_case_number} "
            f"records={verification.actual_record_count} video={verification.video_record_count} "
            f"transcripts={verification.transcript_record_count}"
        )

    ensure_dir(Path(args.output_csv).parent)
    write_csv(Path(args.output_csv), out_rows, OUTPUT_COLUMNS)
    print(f"Wrote {len(out_rows)} inventory rows to {args.output_csv}")


if __name__ == "__main__":
    main()
