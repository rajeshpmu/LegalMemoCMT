from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
    from phase2.hearing_witness_manifest_utils import (
        build_record_cache_from_inventory,
        canonical_language,
        canonical_record_detail_url,
        canonical_record_id,
        classify_examination_type,
        collect_hearing_records,
        estimated_duration_minutes,
        group_records_by_hearing,
        hearing_row_id,
        hearing_session_number,
        has_testimony_signal,
        load_case_numbers_from_manifest,
        pairing_confidence,
        select_preferred_record,
        unique_inventory_rows,
        normalize_case_number,
        normalize_whitespace,
        extract_witness_identity,
    )
else:
    from .common import ensure_dir, read_csv_rows, write_csv
    from .hearing_witness_manifest_utils import (
        build_record_cache_from_inventory,
        canonical_language,
        canonical_record_detail_url,
        canonical_record_id,
        classify_examination_type,
        collect_hearing_records,
        estimated_duration_minutes,
        group_records_by_hearing,
        hearing_row_id,
        hearing_session_number,
        has_testimony_signal,
        load_case_numbers_from_manifest,
        pairing_confidence,
        select_preferred_record,
        unique_inventory_rows,
        normalize_case_number,
        normalize_whitespace,
        extract_witness_identity,
    )


OUTPUT_COLUMNS = [
    "hearing_id",
    "tribunal",
    "case_family",
    "case_number",
    "hearing_date",
    "session_number",
    "record_title",
    "tap_or_record_id",
    "record_detail_url",
    "transcript_record_id",
    "transcript_url",
    "video_record_id",
    "video_url",
    "video_language",
    "transcript_language",
    "expected_duration_minutes",
    "witness_name_or_code",
    "witness_identity_status",
    "examination_type",
    "video_verified",
    "transcript_verified",
    "pairing_status",
    "pairing_confidence",
    "eligible_for_trimodal_dataset",
    "notes",
]


def _tribunal_from_case_number(case_number: str) -> str:
    upper = case_number.upper()
    if upper.startswith("ICTR-"):
        return "ICTR"
    if upper.startswith("IT-"):
        return "ICTY"
    if upper.startswith("MICT-"):
        return "MICT"
    return ""


def _case_family_from_rows(rows: list[dict[str, str]]) -> str:
    for row in rows:
        value = normalize_whitespace(row.get("case_name") or "")
        if value:
            return value
    return ""


def _is_duplicate_row(row: dict[str, object], seen: set[tuple[str, ...]]) -> bool:
    key = (
        normalize_case_number(row.get("case_number") or ""),
        normalize_whitespace(str(row.get("hearing_date") or "")),
        normalize_whitespace(str(row.get("tap_or_record_id") or "")),
        normalize_whitespace(str(row.get("video_url") or "")),
        normalize_whitespace(str(row.get("transcript_url") or "")),
        normalize_whitespace(str(row.get("session_number") or "")),
    )
    if key in seen:
        return True
    seen.add(key)
    return False


def _pairing_status(records: list) -> str:
    video_records = [record for record in records if record.record_kind == "video"]
    transcript_records = [record for record in records if record.record_kind == "transcript"]
    if video_records and transcript_records:
        return "paired"
    if video_records:
        return "video_only"
    if transcript_records:
        return "transcript_only"
    return "unpaired"


def _row_eligible(record_row: dict[str, object]) -> bool:
    if str(record_row.get("pairing_status") or "").strip().lower() != "paired":
        return False
    if str(record_row.get("video_verified") or "").strip().upper() != "YES":
        return False
    if str(record_row.get("transcript_verified") or "").strip().upper() != "YES":
        return False
    if not has_testimony_signal(str(record_row.get("record_title") or "")):
        return False
    return True


def build_hearing_manifest(
    inventory_csv: str | Path,
    video_manifest_csv: str | Path,
    transcript_manifest_csv: str | Path,
    include_case_numbers: set[str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    allowed_cases = load_case_numbers_from_manifest(video_manifest_csv) | load_case_numbers_from_manifest(transcript_manifest_csv)
    if include_case_numbers:
        allowed_cases |= {normalize_case_number(case_number) for case_number in include_case_numbers if normalize_case_number(case_number)}
    if not allowed_cases:
        allowed_cases = set()

    inventory_rows = read_csv_rows(Path(inventory_csv))
    hearing_records = collect_hearing_records(inventory_rows, allowed_cases=allowed_cases or None)
    grouped = group_records_by_hearing(hearing_records)

    out_rows: list[dict[str, object]] = []
    seen_rows: set[tuple[str, ...]] = set()
    case_numbers: set[str] = set()

    for hearing_key, records in sorted(grouped.items(), key=lambda item: item[0]):
        ordered = sorted(
            records,
            key=lambda rec: (
                0 if rec.record_kind == "transcript" else 1,
                0 if canonical_language(rec.row) == "ENG" else 1,
                rec.tape_number if rec.tape_number is not None else 999,
                normalize_whitespace(rec.row.get("document_title") or "").lower(),
                canonical_record_id(rec.row),
            ),
        )
        case_number = normalize_case_number(ordered[0].row.get("case_number") or ordered[0].row.get("record_case_number") or "")
        case_numbers.add(case_number)
        hearing_date = normalize_whitespace(ordered[0].row.get("doc_signature_date") or "")
        session_number = hearing_session_number(ordered)
        video_record = select_preferred_record(ordered, "video")
        transcript_record = select_preferred_record(ordered, "transcript")
        selected = transcript_record or video_record or ordered[0]
        witness_name_or_code, witness_identity_status = extract_witness_identity(selected.row.get("document_title") or "", selected.row.get("case_name") or "")
        if witness_name_or_code != "UNRESOLVED_WITNESS" and witness_identity_status == "unresolved":
            witness_identity_status = "public"

        video_url = canonical_record_detail_url(video_record.row) if video_record else ""
        transcript_url = canonical_record_detail_url(transcript_record.row) if transcript_record else ""
        video_language = canonical_language(video_record.row) if video_record else ""
        transcript_language = canonical_language(transcript_record.row) if transcript_record else ""
        tap_or_record_id = canonical_record_id(video_record.row if video_record else selected.row)
        transcript_record_id = canonical_record_id(transcript_record.row) if transcript_record else ""
        video_record_id = canonical_record_id(video_record.row) if video_record else ""
        record_title = normalize_whitespace((transcript_record or video_record or selected).row.get("document_title") or "")
        tribunal = _tribunal_from_case_number(case_number)
        case_family = normalize_whitespace((selected.row.get("case_name") or _case_family_from_rows([rec.row for rec in ordered])) or "")
        duration_minutes = estimated_duration_minutes(ordered) if video_record and transcript_record else 0
        pairing_status = _pairing_status(ordered)
        confidence = pairing_confidence(ordered)
        expected_duration = duration_minutes if pairing_status == "paired" else 0
        notes_parts = [
            f"source_records={len(ordered)}",
            f"video_records={len([r for r in ordered if r.record_kind == 'video'])}",
            f"transcript_records={len([r for r in ordered if r.record_kind == 'transcript'])}",
            f"witness_status={witness_identity_status}",
        ]
        if any(rec.tape_number is not None for rec in ordered if rec.record_kind == "video"):
            tape_numbers = sorted({rec.tape_number for rec in ordered if rec.record_kind == "video" and rec.tape_number is not None})
            notes_parts.append(f"tape_numbers={','.join(str(n) for n in tape_numbers)}")
        record_row = {
            "hearing_id": hearing_row_id(case_number, hearing_date, record_title, session_number, witness_name_or_code),
            "tribunal": tribunal,
            "case_family": case_family,
            "case_number": case_number,
            "hearing_date": hearing_date,
            "session_number": session_number,
            "record_title": record_title,
            "tap_or_record_id": tap_or_record_id,
            "record_detail_url": video_url or transcript_url,
            "transcript_record_id": transcript_record_id,
            "transcript_url": transcript_url,
            "video_record_id": video_record_id,
            "video_url": video_url,
            "video_language": video_language,
            "transcript_language": transcript_language,
            "expected_duration_minutes": expected_duration,
            "witness_name_or_code": witness_name_or_code,
            "witness_identity_status": witness_identity_status,
            "examination_type": classify_examination_type(record_title),
            "video_verified": "YES" if video_record else "NO",
            "transcript_verified": "YES" if transcript_record else "NO",
            "pairing_status": pairing_status,
            "pairing_confidence": confidence,
            "eligible_for_trimodal_dataset": "YES" if pairing_status == "paired" and has_testimony_signal(record_title) else "NO",
            "notes": "; ".join(notes_parts),
        }
        if _is_duplicate_row(record_row, seen_rows):
            continue
        out_rows.append(record_row)

    out_rows.sort(key=lambda row: (row["tribunal"], row["case_number"], row["hearing_date"], row["record_title"]))
    for row in out_rows:
        if row["pairing_status"] == "paired" and _row_eligible(row):
            row["eligible_for_trimodal_dataset"] = "YES"
        else:
            row["eligible_for_trimodal_dataset"] = "NO"

    summary = {
        "verified_cases": len(case_numbers),
        "hearing_records": len(out_rows),
        "paired_hearings": sum(1 for row in out_rows if row["pairing_status"] == "paired"),
        "video_only_hearings": sum(1 for row in out_rows if row["pairing_status"] == "video_only"),
        "transcript_only_hearings": sum(1 for row in out_rows if row["pairing_status"] == "transcript_only"),
        "resolved_witnesses": 0,
        "protected_witnesses": 0,
        "unresolved_witness_hearings": sum(1 for row in out_rows if row["witness_name_or_code"] == "UNRESOLVED_WITNESS"),
        "trimodal_eligible_hearings": sum(1 for row in out_rows if row["eligible_for_trimodal_dataset"] == "YES"),
        "estimated_trimodal_hours": round(
            sum(float(row["expected_duration_minutes"] or 0) for row in out_rows if row["eligible_for_trimodal_dataset"] == "YES") / 60.0,
            2,
        ),
        "estimated_utterances": 0,
    }
    return out_rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 2 hearing manifest from the verified UCR inventory")
    parser.add_argument("--inventory-csv", default="data/processed/phase2/verified_case_inventory.csv")
    parser.add_argument("--video-manifest-csv", default="data/processed/phase2/ucr_video_candidate_manifest.csv")
    parser.add_argument("--transcript-manifest-csv", default="data/processed/phase2/ucr_transcript_only_manifest.csv")
    parser.add_argument(
        "--include-case-numbers",
        default="",
        help="Comma-separated case numbers to force into the hearing manifest even if they are absent from the media manifests",
    )
    parser.add_argument("--output-csv", default="data/processed/phase2/hearing_manifest.csv")
    parser.add_argument("--summary-json", default="reports/phase2/hearing_witness_manifest_summary.json")
    args = parser.parse_args()

    include_case_numbers = {
        normalize_case_number(item)
        for item in str(args.include_case_numbers or "").split(",")
        if normalize_case_number(item)
    }
    rows, summary = build_hearing_manifest(
        args.inventory_csv,
        args.video_manifest_csv,
        args.transcript_manifest_csv,
        include_case_numbers=include_case_numbers,
    )
    ensure_dir(Path(args.output_csv).parent)
    write_csv(Path(args.output_csv), rows, OUTPUT_COLUMNS)
    ensure_dir(Path(args.summary_json).parent)
    Path(args.summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(rows)} hearing rows to {args.output_csv}")
    print(f"Wrote summary to {args.summary_json}")


if __name__ == "__main__":
    main()
