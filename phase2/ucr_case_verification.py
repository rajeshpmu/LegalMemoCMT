from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests

from .common import UCR_BASE_URL


UCR_USER_AGENT = "LegalMemoCMT-Phase2/1.0"
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}
INVALID_CASE_PLACEHOLDERS = {
    "",
    "TBD",
    "TO_BE_FILLED",
    "ICTR CASE FAMILY",
    "MICT CASES",
}


@dataclass
class CaseVerificationResult:
    requested_case_number: str
    query_case_number: str = ""
    resolved_case_number: str = ""
    case_description: str = ""
    official_case_page: str = ""
    case_page_resolved: bool = False
    case_identity_verified: bool = False
    actual_record_count: int = 0
    transcript_record_count: int = 0
    court_recording_count: int = 0
    video_record_count: int = 0
    tap_count: int = 0
    first_record_date: str = ""
    last_record_date: str = ""
    has_transcripts: str = "no"
    has_court_recordings: str = "no"
    has_videos: str = "no"
    verification_status: str = "unresolved"
    verification_notes: str = ""
    records: list[dict[str, object]] = field(default_factory=list)


def normalize_case_number(case_number: object) -> str:
    text = str(case_number or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return text.strip()


def is_placeholder_case_number(case_number: object) -> bool:
    text = normalize_case_number(case_number)
    if not text:
        return True
    upper = text.upper()
    if upper in INVALID_CASE_PLACEHOLDERS:
        return True
    if "TO_BE_FILLED" in upper:
        return True
    if upper.startswith("TBD"):
        return True
    if "CASE FAMILY" in upper:
        return True
    if upper == "MICT CASES":
        return True
    return False


def case_page_url(case_number: str) -> str:
    return f"{UCR_BASE_URL}/scasedocs/case/{quote(case_number, safe='')}"


def _candidate_case_numbers(case_number: object) -> list[str]:
    raw = str(case_number or "").strip()
    if not raw:
        return []

    if re.search(r"\s+/\s+", raw):
        raw_parts = [part.strip() for part in re.split(r"\s+/\s+", raw) if part.strip()]
    else:
        raw_parts = [raw]

    candidates: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        normalized = normalize_case_number(part)
        if not normalized:
            continue
        extra_candidates = []
        if normalized.upper() in {"ICTR-96-4-T", "ICTR-96-4"}:
            extra_candidates.extend(["ICTR-96-04", "ICTR-96-4-T", "ICTR-96-4"])
        for candidate in ([normalized] + extra_candidates + [normalized[:-2] if normalized.upper().endswith("-T") else ""]):
            if candidate and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    return candidates


def _fetch_json(path: str, params: dict[str, str], session: requests.Session | None = None) -> dict[str, object]:
    getter = session.get if session is not None else requests.get
    response = getter(
        f"{UCR_BASE_URL}{path}",
        params=params,
        timeout=60,
        headers={"User-Agent": UCR_USER_AGENT},
        verify=True,
    )
    response.raise_for_status()
    return response.json()


def _decode_data(payload: dict[str, object]) -> list[dict[str, object]]:
    raw = payload.get("data", [])
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except Exception:
            return []
        return decoded if isinstance(decoded, list) else []
    if isinstance(raw, list):
        return raw
    return []


def fetch_case_detail(case_number: str, session: requests.Session | None = None) -> list[dict[str, object]]:
    payload = _fetch_json("/api/Summary/ByCaseDetail", {"CaseNumber": case_number}, session=session)
    return _decode_data(payload)


def fetch_case_docs_by_lang(case_number: str, *, lang: str = "ENG", session: requests.Session | None = None) -> list[dict[str, object]]:
    payload = _fetch_json("/api/Summary/ByCaseDocsByLang", {"CaseNumber": case_number, "Lang": lang}, session=session)
    return _decode_data(payload)


def fetch_case_related_docs(case_number: str, session: requests.Session | None = None) -> list[dict[str, object]]:
    payload = _fetch_json("/api/Summary/ByCaseRelatedDocs", {"CaseNumber": case_number}, session=session)
    return _decode_data(payload)


def normalize_document_path(document_path: object) -> str:
    text = str(document_path or "").strip()
    if not text:
        return ""
    text = text.replace("http://icr.icty.org/", "https://ucr.irmct.org/")
    text = text.replace("http%3A//icr.icty.org/", "https://ucr.irmct.org/")
    text = text.replace("#", "%23")
    return text


def _record_case_number(row: dict[str, object]) -> str:
    return normalize_case_number(row.get("CaseNumber") or "")


def _record_identity_key(row: dict[str, object]) -> tuple[str, ...]:
    return (
        str(row.get("IndexManagementId") or "").strip(),
        str(row.get("DocumentId") or "").strip(),
        str(row.get("RecordID") or "").strip(),
        _record_case_number(row),
        str(row.get("DocumentTitle") or "").strip(),
        str(row.get("DocSignatureDate") or "").strip(),
        str(row.get("DocumentType") or "").strip().upper(),
        str(row.get("DocumentSource") or "").strip().upper(),
        normalize_document_path(row.get("DocumentPath") or ""),
    )


def _matches_case_family(record_case_number: str, resolved_case_number: str) -> bool:
    record_case_number = normalize_case_number(record_case_number)
    resolved_case_number = normalize_case_number(resolved_case_number)
    if not record_case_number or not resolved_case_number:
        return False
    if record_case_number == resolved_case_number:
        return True
    if record_case_number.startswith(resolved_case_number):
        suffix = record_case_number[len(resolved_case_number) :]
        if suffix.startswith(("-", "/")):
            return True
    return False


def _record_has_video_media(row: dict[str, object]) -> bool:
    document_type = str(row.get("DocumentType") or "").strip().upper()
    document_path = normalize_document_path(row.get("DocumentPath") or "")
    suffix = Path(document_path.split("?", 1)[0]).suffix.lower()
    return document_type == "TAP" or suffix in VIDEO_EXTENSIONS


def _record_is_transcript(row: dict[str, object]) -> bool:
    document_type = str(row.get("DocumentType") or "").strip().upper()
    doc_type_desc = str(row.get("DocTypeDesc") or "").strip().upper()
    document_path = normalize_document_path(row.get("DocumentPath") or "")
    return document_type == "TRA" or "TRANSCRIPT" in doc_type_desc or "/TRANSCRIPT/" in document_path.upper()


def _record_is_court_recording(row: dict[str, object]) -> bool:
    document_type = str(row.get("DocumentType") or "").strip().upper()
    doc_type_desc = str(row.get("DocTypeDesc") or "").strip().upper()
    return document_type == "TAP" or "COURT RECORDINGS" in doc_type_desc or _record_has_video_media(row)


def _parse_record_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _sort_key(row: dict[str, object]) -> tuple[datetime, str, str]:
    parsed = _parse_record_date(row.get("DocSignatureDate")) or datetime.max
    return parsed, normalize_case_number(row.get("CaseNumber") or ""), str(row.get("DocumentTitle") or "")


def resolve_case_verification(
    requested_case_number: object,
    *,
    session: requests.Session | None = None,
    lang: str = "ENG",
) -> CaseVerificationResult:
    requested = normalize_case_number(requested_case_number)
    result = CaseVerificationResult(requested_case_number=requested)

    if is_placeholder_case_number(requested):
        result.verification_status = "invalid_case_number"
        result.verification_notes = "placeholder or non-specific case number rejected before UCR requests"
        result.case_page_resolved = False
        result.case_identity_verified = False
        result.has_transcripts = "unknown"
        result.has_court_recordings = "unknown"
        result.has_videos = "unknown"
        return result

    candidates = _candidate_case_numbers(requested)
    resolved_detail: list[dict[str, object]] = []
    resolved_query = ""
    for candidate in candidates:
        detail_rows = fetch_case_detail(candidate, session=session)
        if detail_rows:
            resolved_detail = detail_rows
            resolved_query = candidate
            break

    if not resolved_detail:
        result.verification_status = "unresolved"
        result.verification_notes = "no case detail returned by /api/Summary/ByCaseDetail"
        return result

    canonical_case_number = normalize_case_number(resolved_detail[0].get("CaseNumber") or resolved_query)
    case_description = str(resolved_detail[0].get("CaseDescription") or "").strip()
    result.query_case_number = resolved_query
    result.resolved_case_number = canonical_case_number
    result.case_description = case_description
    result.official_case_page = case_page_url(canonical_case_number)
    result.case_page_resolved = True

    docs_by_lang = fetch_case_docs_by_lang(canonical_case_number, lang=lang, session=session)
    related_docs = fetch_case_related_docs(canonical_case_number, session=session)

    filtered_records: list[dict[str, object]] = []
    seen_keys: set[tuple[str, ...]] = set()
    for source_endpoint, rows in (("ByCaseDocsByLang", docs_by_lang), ("ByCaseRelatedDocs", related_docs)):
        for row in rows:
            record_case_number = _record_case_number(row)
            if not _matches_case_family(record_case_number, canonical_case_number):
                continue
            if not any(str(row.get(field) or "").strip() for field in ("DocumentTitle", "DocumentPath", "DocumentType", "IndexManagementId", "DocumentId", "RecordID")):
                continue
            identity = _record_identity_key(row)
            if identity in seen_keys:
                continue
            seen_keys.add(identity)
            normalized_row = {
                **row,
                "source_endpoint": source_endpoint,
                "requested_case_number": requested,
                "resolved_case_number": canonical_case_number,
                "record_case_number": record_case_number,
                "DocumentPath": normalize_document_path(row.get("DocumentPath") or ""),
            }
            filtered_records.append(normalized_row)

    filtered_records.sort(key=_sort_key)

    result.records = filtered_records
    result.actual_record_count = len(filtered_records)
    result.transcript_record_count = sum(1 for row in filtered_records if _record_is_transcript(row))
    result.court_recording_count = sum(1 for row in filtered_records if _record_is_court_recording(row))
    result.video_record_count = sum(1 for row in filtered_records if _record_has_video_media(row))
    result.tap_count = sum(1 for row in filtered_records if str(row.get("DocumentType") or "").strip().upper() == "TAP")

    dates = [parsed for parsed in (_parse_record_date(row.get("DocSignatureDate")) for row in filtered_records) if parsed is not None]
    if dates:
        result.first_record_date = min(dates).date().isoformat()
        result.last_record_date = max(dates).date().isoformat()

    result.has_transcripts = "yes" if result.transcript_record_count > 0 else "no"
    result.has_court_recordings = "yes" if result.court_recording_count > 0 else "no"
    result.has_videos = "yes" if result.video_record_count > 0 else "no"
    result.case_identity_verified = bool(filtered_records)
    result.verification_status = "verified" if filtered_records else "unresolved"
    if filtered_records:
        result.verification_notes = (
            f"resolved via {resolved_query}; "
            f"extracted {result.actual_record_count} case-traceable records from ByCaseDocsByLang and ByCaseRelatedDocs"
        )
    else:
        result.verification_notes = (
            f"case detail resolved as {canonical_case_number}, but no case-traceable records were extracted"
        )
    return result


def validation_summary(result: CaseVerificationResult) -> dict[str, object]:
    return {
        "requested_case_number": result.requested_case_number,
        "query_case_number": result.query_case_number,
        "resolved_case_number": result.resolved_case_number,
        "case_page_resolved": result.case_page_resolved,
        "case_identity_verified": result.case_identity_verified,
        "actual_record_count": result.actual_record_count,
        "transcript_record_count": result.transcript_record_count,
        "court_recording_count": result.court_recording_count,
        "video_record_count": result.video_record_count,
        "tap_count": result.tap_count,
        "first_record_date": result.first_record_date,
        "last_record_date": result.last_record_date,
        "has_transcripts": result.has_transcripts,
        "has_court_recordings": result.has_court_recordings,
        "has_videos": result.has_videos,
        "verification_status": result.verification_status,
        "verification_notes": result.verification_notes,
    }
