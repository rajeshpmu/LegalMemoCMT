from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from .common import read_csv_rows, sha1_short


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
LANGUAGE_NORMALIZATION = {
    "english": "eng",
    "french": "fra",
    "floor": "floor",
    "kinyarwanda": "kin",
    "bcs": "bcs",
}
MONTH_TOKENS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}
STOPWORD_TOKENS = {
    "a",
    "an",
    "and",
    "audio",
    "audiofile",
    "are",
    "as",
    "at",
    "by",
    "caviardee",
    "closed",
    "compte",
    "conf",
    "conference",
    "continued",
    "continuation",
    "court",
    "dated",
    "defence",
    "defense",
    "dialogue",
    "document",
    "english",
    "episode",
    "floor",
    "from",
    "held",
    "hearing",
    "html",
    "index",
    "law",
    "of",
    "open",
    "order",
    "public",
    "recording",
    "relevant",
    "redacted",
    "regarding",
    "rasprave",
    "session",
    "status",
    "the",
    "transcript",
    "transcription",
    "translation",
    "video",
    "witness",
    "with",
}
PAIRED_TITLE_HINTS = {
    "hearing",
    "session",
    "transcript",
    "video",
    "recording",
    "court",
    "motion",
    "rule",
    "appeal",
    "status",
    "audience",
}
NON_TESTIMONY_TITLE_HINTS = {
    "judgment",
    "judgement",
    "decision",
    "order",
    "appeal judgment",
    "appeal judgement",
    "sentencing",
}


@dataclass(frozen=True)
class HearingRecord:
    row: dict[str, str]
    record_kind: str
    hearing_key: str
    descriptor_key: str
    tape_number: int | None
    title_tokens: tuple[str, ...]


def load_case_numbers_from_manifest(path: str | Path) -> set[str]:
    numbers: set[str] = set()
    if not Path(path).exists():
        return numbers
    for row in read_csv_rows(Path(path)):
        case_number = (row.get("case_number") or row.get("resolved_case_number") or "").strip()
        if case_number:
            numbers.add(case_number)
    return numbers


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_case_number(case_number: object) -> str:
    text = normalize_whitespace(str(case_number or ""))
    if not text:
        return ""
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return text


def _document_suffix(path: str) -> str:
    parsed = urlparse(path)
    suffix = Path(parsed.path).suffix.lower()
    return suffix


def record_kind(row: dict[str, str]) -> str:
    document_type = (row.get("document_type") or "").strip().upper()
    path = (row.get("document_path") or "").strip()
    suffix = _document_suffix(path)
    if document_type == "TAP":
        if suffix in VIDEO_EXTENSIONS:
            return "video"
        if suffix in AUDIO_EXTENSIONS:
            return "audio"
        return "video"
    if document_type == "TRA":
        return "transcript"
    return "other"


def _parse_tape_number(title: str) -> int | None:
    match = re.search(r"\btape\s*(\d+)\b", title, re.I)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None
    return None


def _tokenize_title(title: str) -> list[str]:
    text = normalize_whitespace(title).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [tok for tok in text.split() if tok]
    return tokens


def title_descriptor(title: str) -> str:
    tokens = []
    for token in _tokenize_title(title):
        if token in STOPWORD_TOKENS:
            continue
        if token in MONTH_TOKENS:
            continue
        if token.isdigit():
            continue
        if token in LANGUAGE_NORMALIZATION:
            continue
        if len(token) == 1 and token in {"i", "v"}:
            continue
        tokens.append(token)
    descriptor = " ".join(tokens).strip()
    return descriptor or "generic"


def hearing_key(row: dict[str, str]) -> str:
    case_number = normalize_case_number(row.get("case_number") or row.get("record_case_number") or "")
    date = normalize_whitespace(row.get("doc_signature_date") or "")
    return "|".join([case_number, date])


def hearing_is_candidate(row: dict[str, str]) -> bool:
    kind = record_kind(row)
    if kind not in {"video", "transcript"}:
        return False
    title = normalize_whitespace(row.get("document_title") or "").lower()
    if any(term in title for term in NON_TESTIMONY_TITLE_HINTS):
        return False
    if kind == "video":
        return True
    return any(term in title for term in PAIRED_TITLE_HINTS)


def extract_witness_identity(title: str, case_name: str = "") -> tuple[str, str]:
    text = normalize_whitespace(title)
    lowered = text.lower()

    protected_patterns = [
        r"\bRM\d{2,4}\b",
        r"\bPW\d{2,4}\b",
        r"\bWitness\s+[A-Z]{1,3}\b",
        r"\bProtected\s+Witness\s+[A-Z0-9]{1,8}\b",
    ]
    for pattern in protected_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0).strip(), "protected"

    public_patterns = [
        r"\bWitness\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\b",
        r"\bTestimony\s+of\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\b",
    ]
    for pattern in public_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = normalize_whitespace(match.group(1))
            if candidate:
                return candidate, "public"

    return "UNRESOLVED_WITNESS", "unresolved"


def classify_examination_type(title: str) -> str:
    text = normalize_whitespace(title).lower()
    if "recross" in text:
        return "recross_examination"
    if "redirect" in text or "re-direct" in text:
        return "redirect_examination"
    if "cross examination" in text or "cross-examination" in text or "cross examination" in text:
        return "cross_examination"
    if "direct examination" in text or "examination-in-chief" in text:
        return "direct_examination"
    if "court question" in text or "questions from the bench" in text or "bench" in text:
        return "court_questioning"
    return "unknown"


def canonical_language(row: dict[str, str]) -> str:
    for field in ("document_language", "language", "lang"):
        value = normalize_whitespace(row.get(field) or "")
        if value:
            normalized = LANGUAGE_NORMALIZATION.get(value.lower(), value.lower())
            return normalized.upper() if len(normalized) > 3 else normalized.upper()
    path = normalize_whitespace(row.get("document_path") or "").lower()
    if "/public/english/" in path:
        return "ENG"
    if "/public/french/" in path:
        return "FRA"
    if "/public/other/" in path:
        return "OTHER"
    if "/public/bcs/" in path:
        return "BCS"
    return ""


def canonical_record_id(row: dict[str, str]) -> str:
    for field in ("record_id", "document_id", "index_management_id", "inventory_id"):
        value = normalize_whitespace(row.get(field) or "")
        if value:
            return value
    return ""


def canonical_record_detail_url(row: dict[str, str]) -> str:
    return normalize_whitespace(row.get("document_path") or "")


def unique_inventory_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = (
            normalize_case_number(row.get("case_number") or row.get("record_case_number") or ""),
            normalize_whitespace(row.get("doc_signature_date") or ""),
            normalize_whitespace(row.get("document_title") or ""),
            normalize_whitespace(row.get("document_path") or ""),
            normalize_whitespace(row.get("document_type") or "").upper(),
            normalize_whitespace(row.get("index_management_id") or ""),
            normalize_whitespace(row.get("document_id") or ""),
            normalize_whitespace(row.get("record_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def collect_hearing_records(
    inventory_rows: list[dict[str, str]],
    *,
    allowed_cases: set[str] | None = None,
) -> list[HearingRecord]:
    records: list[HearingRecord] = []
    for row in unique_inventory_rows(inventory_rows):
        case_number = normalize_case_number(row.get("case_number") or row.get("record_case_number") or "")
        if allowed_cases and case_number not in allowed_cases:
            continue
        if not hearing_is_candidate(row):
            continue
        kind = record_kind(row)
        descriptor = title_descriptor(row.get("document_title") or "")
        hearing = hearing_key(row)
        tape_number = _parse_tape_number(row.get("document_title") or "") if kind == "video" else None
        tokens = tuple(_tokenize_title(row.get("document_title") or ""))
        records.append(
            HearingRecord(
                row=row,
                record_kind=kind,
                hearing_key=hearing,
                descriptor_key=descriptor,
                tape_number=tape_number,
                title_tokens=tokens,
            )
        )
    return records


def group_records_by_hearing(records: Iterable[HearingRecord]) -> dict[str, list[HearingRecord]]:
    grouped: dict[str, list[HearingRecord]] = defaultdict(list)
    for record in records:
        grouped[record.hearing_key].append(record)
    return grouped


def select_preferred_record(records: list[HearingRecord], kind: str) -> HearingRecord | None:
    preferred = [record for record in records if record.record_kind == kind]
    if not preferred:
        return None

    def sort_key(record: HearingRecord) -> tuple[int, int, int, str, str]:
        row = record.row
        lang = canonical_language(row)
        language_rank = 0 if lang in {"ENG", "EN"} else 1 if lang else 2
        tape_rank = record.tape_number if record.tape_number is not None else 999
        title_rank = 0 if "english" in (row.get("document_title") or "").lower() else 1
        return (
            language_rank,
            tape_rank,
            title_rank,
            normalize_whitespace(row.get("document_title") or "").lower(),
            canonical_record_id(row),
        )

    return sorted(preferred, key=sort_key)[0]


def hearing_session_number(records: list[HearingRecord]) -> str:
    video_numbers = sorted({record.tape_number for record in records if record.record_kind == "video" and record.tape_number is not None})
    if video_numbers:
        if len(video_numbers) == 1:
            return str(video_numbers[0])
        return f"{video_numbers[0]}-{video_numbers[-1]}"
    return ""


def estimated_duration_minutes(records: list[HearingRecord]) -> int:
    video_numbers = sorted({record.tape_number for record in records if record.record_kind == "video" and record.tape_number is not None})
    if video_numbers:
        return 60 * len(video_numbers)
    if any(record.record_kind == "video" for record in records):
        return 60
    return 0


def has_testimony_signal(record_title: str) -> bool:
    text = normalize_whitespace(record_title).lower()
    if any(term in text for term in NON_TESTIMONY_TITLE_HINTS):
        return False
    return any(term in text for term in PAIRED_TITLE_HINTS)


def hearing_group_summary(records: list[HearingRecord]) -> dict[str, object]:
    video_records = [record for record in records if record.record_kind == "video"]
    transcript_records = [record for record in records if record.record_kind == "transcript"]
    return {
        "video_count": len(video_records),
        "transcript_count": len(transcript_records),
        "video_tape_numbers": sorted({record.tape_number for record in video_records if record.tape_number is not None}),
        "video_languages": sorted({canonical_language(record.row) for record in video_records if canonical_language(record.row)}),
        "transcript_languages": sorted({canonical_language(record.row) for record in transcript_records if canonical_language(record.row)}),
        "record_ids": [canonical_record_id(record.row) for record in records if canonical_record_id(record.row)],
    }


def build_record_cache_from_inventory(
    inventory_csv: str | Path,
    *,
    allowed_cases: set[str] | None = None,
) -> list[HearingRecord]:
    rows = read_csv_rows(Path(inventory_csv))
    return collect_hearing_records(rows, allowed_cases=allowed_cases)


def pairing_confidence(records: list[HearingRecord]) -> str:
    video_records = [record for record in records if record.record_kind == "video"]
    transcript_records = [record for record in records if record.record_kind == "transcript"]
    if not video_records or not transcript_records:
        return ""
    return "high"


def hearing_row_id(case_number: str, hearing_date: str, record_title: str, session_number: str, witness: str) -> str:
    return f"hear_{sha1_short('|'.join([case_number, hearing_date, record_title, session_number, witness]), length=16)}"
