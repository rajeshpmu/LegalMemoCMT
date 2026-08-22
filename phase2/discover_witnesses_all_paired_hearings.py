from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir
    from phase2.trimodal_validation_utils import (
        count_utterances,
        csv_rows,
        csv_write,
        detect_examination_type,
        extract_transcript_text,
        maybe_download_transcript,
        normalize_case_number,
        normalize_text,
        has_witness_testimony,
    )
else:
    from .common import ensure_dir
    from .trimodal_validation_utils import (
        count_utterances,
        csv_rows,
        csv_write,
        detect_examination_type,
        extract_transcript_text,
        maybe_download_transcript,
        normalize_case_number,
        normalize_text,
        has_witness_testimony,
    )


HEARING_INPUT = Path("data/processed/phase2/hearing_manifest.csv")
VALIDATED_HEARING_INPUT = Path("data/processed/phase2/hearing_manifest_validated.csv")
VALIDATED_WITNESS_INPUT = Path("data/processed/phase2/witness_manifest_validated.csv")
SUMMARY_INPUT = Path("reports/phase2/trimodal_validation_summary.json")
OUTPUT_CSV = Path("data/processed/phase2/paired_hearing_witness_discovery.csv")
CACHE_DIR = Path("data/phase2/corpus_selection_cache/transcripts")
LOCAL_TRANSCRIPT_DIR = Path("data/processed/phase2/transcripts")

WITNESS_SECTION_RE = re.compile(r"^\s*WITNESS(?:ES)?\b", re.I)
EXHIBIT_SECTION_RE = re.compile(r"^\s*EXHIBIT(?:S)?\b", re.I)
PAGE_LINE_RE = re.compile(r"^(?P<content>.*?)(?:\s+|\t)(?P<page>\d+)\s*$")
EXAM_RE = re.compile(
    r"(direct examination|cross[- ]examination|re[- ]?examination|re[- ]?direct|recross|court questioning|questions from the bench|questioning by the judges|examination-in-chief)",
    re.I,
)
SIMPLE_TESTIMONY_RE = re.compile(r"(?im)^\s*(THE\s+)?WITNESS\b[:\-]|\bQ\s*[:.]\s*\S|\bA\s*[:.]\s*\S")
SHORT_RESPONSE_SET = {
    "yes",
    "no",
    "okay",
    "ok",
    "right",
    "correct",
    "indeed",
    "thank you",
    "thankyou",
    "yes sir",
    "no sir",
    "yes ma'am",
    "no ma'am",
}


def _load_map(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = csv_rows(path)
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        hearing_id = normalize_text(row.get("hearing_id"))
        if hearing_id:
            out[hearing_id] = row
    return out


def _clean_candidate(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"\((?:continued|commenced[^)]*|closed session[^)]*)\)", "", text, flags=re.I)
    text = re.sub(r"\bcontinued\b", "", text, flags=re.I)
    text = re.sub(r"[\.·…]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -:\t")


def _split_pages(text: str) -> list[str]:
    pages = text.split("\f")
    return pages if pages else [text]


def _front_matter(text: str) -> str:
    upper = text.upper()
    markers = [upper.find("P R O C E E D I N G S"), upper.find("PROCEEDINGS")]
    markers = [m for m in markers if m >= 0]
    if not markers:
        return text
    return text[: min(markers)]


def _body(text: str) -> str:
    upper = text.upper()
    markers = [upper.find("P R O C E E D I N G S"), upper.find("PROCEEDINGS")]
    markers = [m for m in markers if m >= 0]
    if not markers:
        return text
    return text[min(markers) :]


def _parse_page_number(line: str) -> tuple[str, int | None]:
    m = PAGE_LINE_RE.match(normalize_text(line))
    if not m:
        return normalize_text(line), None
    content = normalize_text(m.group("content"))
    try:
        page = int(m.group("page"))
    except Exception:
        page = None
    return content, page


def _extract_index_lines(text: str) -> list[str]:
    front = _front_matter(text)
    lines: list[str] = []
    for raw in front.splitlines():
        line = normalize_text(raw)
        if line:
            lines.append(line)
    return lines


def _candidate_status(candidate: str) -> str:
    text = normalize_text(candidate)
    if not text:
        return "IGNORE"
    up = text.upper()
    if any(
        text.lower().startswith(prefix)
        for prefix in [
            "for the ",
            "before the ",
            "court reporters",
            "exhibit",
            "exhibits",
            "examination",
            "cross-examination",
            "re-examination",
            "re-direct",
            "recross",
            "the prosecutor",
            "the registry",
            "the court",
        ]
    ):
        return "IGNORE"
    if re.fullmatch(r"(?:RM|PW|DH)\d{2,5}", up) or re.fullmatch(r"[A-Z]{2,4}\d{1,5}", up):
        return "PROTECTED_CODE"
    if re.fullmatch(r"[A-Z]{1,4}\d{0,4}", up) and any(ch.isdigit() for ch in up):
        return "PROTECTED_CODE"
    if len(text.split()) >= 2 and not any(term in text.lower() for term in ["for the", "witness", "defence", "defense"]):
        if re.fullmatch(r"[A-Za-zÀ-ÿ'’\-.]+(?:\s+[A-Za-zÀ-ÿ'’\-.]+){1,5}", text):
            return "PUBLIC_NAME"
    return "UNRESOLVED_WITNESS"


def _extract_index_candidates(text: str) -> list[dict[str, object]]:
    lines = _extract_index_lines(text)
    if not lines:
        lines = []
    in_witness_section = False
    candidates: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    pending_start_page: int | None = None

    seen_candidates: set[str] = set()

    for match in re.finditer(r"(?im)^\s*(?:WITNESS|THE WITNESS)\s+([A-Z]{1,4}\d{0,4}|[A-Z]{2,4})\b", text):
        candidate = _clean_candidate(match.group(1))
        status = _candidate_status(candidate)
        if status == "PROTECTED_CODE" and candidate not in seen_candidates:
            candidates.append(
                {
                    "candidate": candidate,
                    "status": status,
                    "start_page": None,
                    "end_page": None,
                    "start_marker": f"WITNESS {candidate}",
                    "exam_lines": [],
                }
            )
            seen_candidates.add(candidate)

    for raw in lines:
        line, page = _parse_page_number(raw)
        upper = line.upper()
        if WITNESS_SECTION_RE.match(line):
            in_witness_section = True
            continue
        if EXHIBIT_SECTION_RE.match(line):
            break
        if not in_witness_section:
            continue
        if not line or upper in {"WITNESS", "WITNESSES"}:
            continue
        if EXAM_RE.search(line):
            if current is not None:
                current.setdefault("exam_lines", []).append(line)
                if pending_start_page is not None and current.get("start_page") in {None, ""}:
                    current["start_page"] = pending_start_page
                if page is not None:
                    current["end_page"] = page
            continue

        candidate = ""
        if upper.startswith("WITNESS "):
            candidate = _clean_candidate(line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else "")
        elif page is not None:
            candidate = _clean_candidate(line)
        elif current is None and len(line.split()) <= 8:
            candidate = _clean_candidate(line)

        if not candidate:
            continue

        status = _candidate_status(candidate)
        if status == "IGNORE":
            continue

        if current is not None and current.get("candidate") != candidate:
            candidates.append(current)
            current = None

        if current is None:
            current = {
                "candidate": candidate,
                "status": status,
                "start_page": page,
                "end_page": page,
                "start_marker": line,
                "exam_lines": [],
            }
        else:
            if current.get("start_page") in {None, ""} and page is not None:
                current["start_page"] = page
            current["end_page"] = page or current.get("end_page")

        seen_candidates.add(candidate)

        if page is None and current.get("start_page") in {None, ""}:
            pending_start_page = pending_start_page or None
        elif page is not None:
            pending_start_page = page

    if current is not None:
        candidates.append(current)

    cleaned: list[dict[str, object]] = []
    for candidate in candidates:
        name = _clean_candidate(str(candidate.get("candidate") or ""))
        if not name:
            continue
        status = _candidate_status(name)
        if status == "IGNORE":
            continue
        candidate["candidate"] = name
        candidate["status"] = status
        cleaned.append(candidate)
    return cleaned


def _transcript_markers(text: str, candidate: str) -> tuple[str, str, bool]:
    body = _body(text)
    pages = _split_pages(text)
    start_marker = ""
    end_marker = ""
    contains = False
    for page in pages:
        if not start_marker and (re.search(r"(?im)^\s*(?:THE\s+)?WITNESS\b[:\-]?", page) or candidate.upper() in page.upper()):
            start_marker = _clean_candidate(next((ln for ln in page.splitlines() if "WITNESS" in ln.upper() or candidate.upper() in ln.upper()), ""))
            contains = True
        if re.search(r"(?im)^\s*(?:THE\s+)?WITNESS\b[:\-]?", page) or re.search(r"(?im)^\s*[QA]\s*[:.]\s*\S", page):
            contains = True
            end_marker = _clean_candidate(next((ln for ln in reversed(page.splitlines()) if ln.strip()), ""))
    if not start_marker:
        marker = re.search(r"(?im)^\s*(?:THE\s+)?WITNESS\b[:\-]?\s*(.*)$", body)
        if marker:
            start_marker = _clean_candidate(marker.group(0))
            contains = True
    if not end_marker and contains:
        end_marker = "END_OF_TESTIMONY"
    return start_marker, end_marker, contains


def _utterance_turns(text: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    current_label = ""
    current_text: list[str] = []

    def flush() -> None:
        nonlocal current_label, current_text
        joined = normalize_text(" ".join(current_text))
        if joined:
            turns.append((current_label or "UNKNOWN", joined))
        current_label = ""
        current_text = []

    for raw in text.splitlines():
        line = normalize_text(raw)
        if not line:
            continue
        if re.fullmatch(r"[IVXLC]+\.*", line):
            continue
        if line.upper().startswith("PAGE "):
            continue
        m = re.match(r"^(?P<label>[A-Z][A-Z0-9 .,'()\/\-]{1,60})\s*:\s*(?P<text>.*)$", line)
        if m:
            flush()
            current_label = normalize_text(m.group("label"))
            if m.group("text"):
                current_text.append(normalize_text(m.group("text")))
            continue
        q = re.match(r"^(?P<label>[QA])\s*[:.]\s*(?P<text>.*)$", line, re.I)
        if q:
            flush()
            current_label = q.group("label").upper()
            if q.group("text"):
                current_text.append(normalize_text(q.group("text")))
            continue
        if current_label:
            current_text.append(line)
        elif len(line) > 2:
            current_label = "UNKNOWN"
            current_text.append(line)

    flush()
    return turns


def _classify_label(label: str) -> str:
    up = normalize_text(label).upper()
    if up in {"Q", "QUESTION"}:
        return "question"
    if up in {"A", "ANSWER"}:
        return "answer"
    if "JUDGE" in up or "PRESIDENT" in up or up.startswith("MR. PRESIDENT") or up.startswith("THE COURT"):
        return "judge"
    if "WITNESS" in up or up in {"UNKNOWN"}:
        return "witness"
    if any(term in up for term in ["PROSECUTOR", "COUNSEL", "MR.", "MS.", "MRS.", "DEFENCE", "DEFENSE", "ATTORNEY"]):
        return "counsel"
    return "counsel"


def _short_response(text: str) -> bool:
    cleaned = normalize_text(text).lower().strip(" .!?")
    if not cleaned:
        return True
    if cleaned in SHORT_RESPONSE_SET:
        return True
    words = cleaned.split()
    return len(words) <= 2


def _parse_candidate_rows(
    hearing_row: dict[str, str],
    transcript_text: str,
    transcript_path: Path,
) -> list[dict[str, object]]:
    pages = _split_pages(transcript_text)
    candidates = _extract_index_candidates(transcript_text)
    if not candidates:
        fallback_name = normalize_text(hearing_row.get("witness_name_or_code"))
        fallback_status = normalize_text(hearing_row.get("witness_identity_status")).upper()
        if fallback_name and fallback_status in {"PUBLIC_NAME", "PROTECTED_CODE"}:
            candidates = [
                {
                    "candidate": fallback_name,
                    "status": fallback_status,
                    "start_page": 1,
                    "end_page": len(pages),
                    "start_marker": fallback_name,
                    "exam_lines": [],
                }
            ]

    if not candidates:
        return [
            {
                "witness_name_or_code": "UNRESOLVED_WITNESS",
                "witness_identity_status": "NO_WITNESS_TESTIMONY" if not has_witness_testimony(transcript_text) else "UNRESOLVED_WITNESS",
                "witness_resolution_confidence": "low",
                "testimony_start_page": "",
                "testimony_end_page": "",
                "testimony_start_marker": "",
                "testimony_end_marker": "",
                "contains_actual_witness_testimony": "NO" if not has_witness_testimony(transcript_text) else "YES",
                "non_witness_hearing_reason": "no_witness_markers" if not has_witness_testimony(transcript_text) else "unresolved_witness",
                "raw_witness_utterance_count": 0,
                "usable_witness_utterance_estimate": 0,
                "short_response_count": 0,
                "question_utterance_count": 0,
                "answer_utterance_count": 0,
                "question_answer_pair_count": 0,
                "estimated_testimony_minutes": 0,
                "examination_types_present": "",
                "transcript_speaker_turns": 0,
                "witness_utterance_count": 0,
                "counsel_utterance_count": 0,
                "judge_utterance_count": 0,
                "segment_text": "",
            }
        ]

    out_rows: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates):
        start_page = candidate.get("start_page")
        if not isinstance(start_page, int) or start_page < 1:
            start_page = 1
        next_start = None
        if idx + 1 < len(candidates):
            next_candidate_page = candidates[idx + 1].get("start_page")
            if isinstance(next_candidate_page, int) and next_candidate_page > start_page:
                next_start = next_candidate_page - 1
        end_page = candidate.get("end_page")
        if not isinstance(end_page, int) or end_page < start_page:
            end_page = next_start or len(pages)
        end_page = min(max(end_page, start_page), len(pages))
        section_pages = pages[start_page - 1 : end_page]
        section_text = "\n\f\n".join(section_pages).strip()
        turns = _utterance_turns(section_text)
        question_turns = [turn for turn in turns if _classify_label(turn[0]) == "question"]
        answer_turns = [turn for turn in turns if _classify_label(turn[0]) == "answer"]
        witness_turns = [turn for turn in turns if _classify_label(turn[0]) == "witness"]
        judge_turns = [turn for turn in turns if _classify_label(turn[0]) == "judge"]
        counsel_turns = [turn for turn in turns if _classify_label(turn[0]) == "counsel"]
        usable = 0
        short_responses = 0
        for _label, utt in witness_turns:
            if _short_response(utt):
                short_responses += 1
            else:
                usable += 1
        q_a_pairs = min(len(question_turns), len(answer_turns))
        status = str(candidate.get("status") or "UNRESOLVED_WITNESS")
        if status == "UNRESOLVED_WITNESS" and witness_turns:
            status = "UNRESOLVED_WITNESS"
        if not witness_turns and not has_witness_testimony(section_text):
            status = "NO_WITNESS_TESTIMONY"
        identity_conf = "high" if status in {"PUBLIC_NAME", "PROTECTED_CODE"} else "low"
        if status == "UNRESOLVED_WITNESS" and witness_turns:
            identity_conf = "medium"
        ex_types = sorted({detect_examination_type(turn[1]) for turn in turns if detect_examination_type(turn[1]) != "unknown"})
        start_marker = normalize_text(candidate.get("start_marker") or "")
        if not start_marker:
            start_marker = normalize_text(next((line for line in section_text.splitlines() if "WITNESS" in line.upper()), ""))
        end_marker = normalize_text(candidate.get("exam_lines")[-1] if candidate.get("exam_lines") else "")
        contains_testimony = "YES" if witness_turns or has_witness_testimony(section_text) else "NO"
        row = {
            "hearing_id": normalize_text(hearing_row.get("hearing_id")),
            "tribunal": normalize_text(hearing_row.get("tribunal")),
            "case_family": normalize_text(hearing_row.get("case_family")),
            "case_number": normalize_case_number(hearing_row.get("case_number")),
            "hearing_date": normalize_text(hearing_row.get("hearing_date")),
            "transcript_url": normalize_text(hearing_row.get("transcript_url")),
            "video_url": normalize_text(hearing_row.get("video_url")),
            "transcript_readable": "YES" if len(section_text.split()) >= 20 else "NO",
            "witness_name_or_code": normalize_text(candidate.get("candidate")),
            "witness_identity_status": status,
            "witness_resolution_confidence": identity_conf,
            "examination_types_present": ";".join(ex_types) if ex_types else "unknown",
            "transcript_speaker_turns": len(turns),
            "witness_utterance_count": len(witness_turns),
            "counsel_utterance_count": len(counsel_turns),
            "judge_utterance_count": len(judge_turns),
            "testimony_start_page": start_page if contains_testimony == "YES" else "",
            "testimony_end_page": end_page if contains_testimony == "YES" else "",
            "testimony_start_marker": start_marker,
            "testimony_end_marker": end_marker,
            "estimated_testimony_minutes": max(0, round(len(turns) * 0.45)),
            "contains_actual_witness_testimony": contains_testimony,
            "non_witness_hearing_reason": "no_witness_markers" if contains_testimony == "NO" else "",
            "transcript_language": normalize_text(hearing_row.get("transcript_language") or hearing_row.get("video_language") or ""),
            "video_language": normalize_text(hearing_row.get("video_language") or ""),
            "notes": f"source_transcript={transcript_path};candidate_source=index;sections={';'.join(ex_types) if ex_types else 'unknown'}",
            "witness_key": "",
            "is_repeat_witness": "NO",
            "witness_hearing_count": 1,
            "cumulative_witness_utterances": len(witness_turns),
            "cumulative_estimated_testimony_minutes": max(0, round(len(turns) * 0.45)),
            "raw_witness_utterance_count": len(witness_turns),
            "usable_witness_utterance_estimate": usable,
            "short_response_count": short_responses,
            "question_utterance_count": len(question_turns),
            "answer_utterance_count": len(answer_turns),
            "question_answer_pair_count": q_a_pairs,
        }
        if status == "NO_WITNESS_TESTIMONY":
            row["non_witness_hearing_reason"] = "procedural_or_non_testimony"
        out_rows.append(row)

    if not out_rows:
        return out_rows

    witness_hearing_map: dict[str, set[str]] = defaultdict(set)
    for row in out_rows:
        status = normalize_text(row.get("witness_identity_status")).upper()
        witness = normalize_text(row.get("witness_name_or_code"))
        if status not in {"PUBLIC_NAME", "PROTECTED_CODE"} or not witness:
            continue
        witness_key = "|".join(
            [
                normalize_text(row.get("tribunal")).upper(),
                normalize_case_number(row.get("case_number")).upper(),
                witness.upper(),
            ]
        )
        row["witness_key"] = witness_key
        witness_hearing_map[witness_key].add(normalize_text(row.get("hearing_id")))

    key_totals_utterances: Counter[str] = Counter()
    key_totals_minutes: Counter[str] = Counter()
    for row in out_rows:
        key = normalize_text(row.get("witness_key"))
        if not key:
            continue
        key_totals_utterances[key] += int(row.get("usable_witness_utterance_estimate") or 0)
        key_totals_minutes[key] += int(row.get("estimated_testimony_minutes") or 0)

    for row in out_rows:
        key = normalize_text(row.get("witness_key"))
        if not key:
            row["is_repeat_witness"] = "NO"
            continue
        count = len(witness_hearing_map.get(key, set()))
        row["witness_hearing_count"] = count
        row["is_repeat_witness"] = "YES" if count > 1 else "NO"
        row["cumulative_witness_utterances"] = key_totals_utterances[key]
        row["cumulative_estimated_testimony_minutes"] = key_totals_minutes[key]

    return out_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover witnesses across all paired hearings using transcript-first parsing")
    parser.add_argument("--hearing-input", default=str(HEARING_INPUT))
    parser.add_argument("--validated-hearing-input", default=str(VALIDATED_HEARING_INPUT))
    parser.add_argument("--validated-witness-input", default=str(VALIDATED_WITNESS_INPUT))
    parser.add_argument("--summary-input", default=str(SUMMARY_INPUT))
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV))
    parser.add_argument("--cache-dir", default=str(CACHE_DIR))
    args = parser.parse_args()

    hearing_rows = csv_rows(args.hearing_input)
    validated_hearing_map = _load_map(Path(args.validated_hearing_input))
    validated_witness_map = _load_map(Path(args.validated_witness_input))
    ensure_dir(Path(args.cache_dir))

    out_rows: list[dict[str, object]] = []
    paired_scanned = 0
    readable_hearings: set[str] = set()
    with_testimony = 0
    unresolved_hearing_ids: set[str] = set()
    non_witness_hearing_ids: set[str] = set()
    public_witnesses: set[str] = set()
    protected_witnesses: set[str] = set()
    distinct_witnesses: set[str] = set()
    repeat_witness_hearings = 0
    raw_witness_utterances = 0
    usable_witness_utterances = 0
    candidate_minutes = 0
    hearing_ids_with_testimony: set[str] = set()
    hearing_ids_with_repeat: set[str] = set()

    for row in hearing_rows:
        if normalize_text(row.get("pairing_status")) != "paired":
            continue
        paired_scanned += 1
        hearing_id = normalize_text(row.get("hearing_id"))
        transcript_url = normalize_text(row.get("transcript_url"))
        transcript_path = None
        for suffix in (".txt", ".doc", ".docx", ".pdf", ".html", ".htm", ".rtf"):
            candidate = LOCAL_TRANSCRIPT_DIR / f"{hearing_id}{suffix}"
            if candidate.exists():
                transcript_path = candidate
                break
        if transcript_path is None:
            transcript_path = maybe_download_transcript(transcript_url, hearing_id, output_dir=Path(args.cache_dir))
        transcript_text, page_count = extract_transcript_text(transcript_path)
        candidate_rows = _parse_candidate_rows(row, transcript_text, transcript_path)
        if not candidate_rows:
            candidate_rows = [
                {
                    "hearing_id": hearing_id,
                    "tribunal": normalize_text(row.get("tribunal")),
                    "case_family": normalize_text(row.get("case_family")),
                    "case_number": normalize_case_number(row.get("case_number")),
                    "hearing_date": normalize_text(row.get("hearing_date")),
                    "transcript_url": transcript_url,
                    "video_url": normalize_text(row.get("video_url")),
                    "transcript_readable": "YES" if len(transcript_text.split()) >= 20 else "NO",
                    "witness_name_or_code": "UNRESOLVED_WITNESS",
                    "witness_identity_status": "NO_WITNESS_TESTIMONY" if not has_witness_testimony(transcript_text) else "UNRESOLVED_WITNESS",
                    "witness_resolution_confidence": "low",
                    "examination_types_present": detect_examination_type(transcript_text),
                    "transcript_speaker_turns": 0,
                    "witness_utterance_count": 0,
                    "counsel_utterance_count": 0,
                    "judge_utterance_count": 0,
                    "testimony_start_page": "",
                    "testimony_end_page": "",
                    "testimony_start_marker": "",
                    "testimony_end_marker": "",
                    "estimated_testimony_minutes": 0,
                    "contains_actual_witness_testimony": "NO",
                    "non_witness_hearing_reason": "no_witness_markers",
                    "transcript_language": normalize_text(row.get("transcript_language") or row.get("video_language") or ""),
                    "video_language": normalize_text(row.get("video_language") or ""),
                    "notes": f"source_transcript={transcript_path};fallback=no_candidate_rows",
                    "witness_key": "",
                    "is_repeat_witness": "NO",
                    "witness_hearing_count": 1,
                    "cumulative_witness_utterances": 0,
                    "cumulative_estimated_testimony_minutes": 0,
                    "raw_witness_utterance_count": 0,
                    "usable_witness_utterance_estimate": 0,
                    "short_response_count": 0,
                    "question_utterance_count": 0,
                    "answer_utterance_count": 0,
                    "question_answer_pair_count": 0,
                }
            ]

        if len(candidate_rows) > 1:
            for candidate_row in candidate_rows:
                if candidate_row.get("witness_identity_status") in {"PUBLIC_NAME", "PROTECTED_CODE"}:
                    candidate_row["notes"] = str(candidate_row.get("notes") or "") + ";multi_witness_hearing=yes"

        hearing_has_testimony = any(str(r.get("contains_actual_witness_testimony")) == "YES" for r in candidate_rows)
        if hearing_has_testimony:
            with_testimony += 1
            hearing_ids_with_testimony.add(hearing_id)
        else:
            non_witness_hearing_ids.add(hearing_id)

        for candidate_row in candidate_rows:
            status = normalize_text(candidate_row.get("witness_identity_status")).upper()
            witness_key = normalize_text(candidate_row.get("witness_key"))
            if status == "PUBLIC_NAME" and witness_key:
                public_witnesses.add(witness_key)
                distinct_witnesses.add(witness_key)
            elif status == "PROTECTED_CODE" and witness_key:
                protected_witnesses.add(witness_key)
                distinct_witnesses.add(witness_key)
            elif status == "UNRESOLVED_WITNESS":
                unresolved_hearing_ids.add(hearing_id)
            elif status == "NO_WITNESS_TESTIMONY":
                non_witness_hearing_ids.add(hearing_id)
            raw_witness_utterances += int(candidate_row.get("raw_witness_utterance_count") or 0)
            usable_witness_utterances += int(candidate_row.get("usable_witness_utterance_estimate") or 0)
            candidate_minutes += int(candidate_row.get("estimated_testimony_minutes") or 0)
            if candidate_row.get("transcript_readable") == "YES":
                readable_hearings.add(hearing_id)
            out_rows.append(candidate_row)

        repeat_hit = any(
            normalize_text(row.get("is_repeat_witness")).upper() == "YES"
            for row in candidate_rows
        )
        if repeat_hit:
            repeat_witness_hearings += 1
            hearing_ids_with_repeat.add(hearing_id)

        if hearing_id in validated_witness_map:
            validated_row = validated_witness_map[hearing_id]
            if normalize_text(validated_row.get("witness_identity_status")).upper() in {"PUBLIC_NAME", "PROTECTED_CODE"}:
                distinct_witnesses.add("|".join([normalize_text(validated_row.get("tribunal")).upper(), normalize_case_number(validated_row.get("case_number")).upper(), normalize_text(validated_row.get("witness_name_or_code")).upper()]))

    if out_rows:
        for row in out_rows:
            status = normalize_text(row.get("witness_identity_status")).upper()
            if status in {"PUBLIC_NAME", "PROTECTED_CODE"} and row.get("witness_key"):
                row["witness_identity_status"] = status
            elif status not in {"PUBLIC_NAME", "PROTECTED_CODE", "MULTIPLE_WITNESSES", "NO_WITNESS_TESTIMONY"}:
                row["witness_identity_status"] = "UNRESOLVED_WITNESS"

    csv_write(
        args.output_csv,
        out_rows,
        [
            "hearing_id",
            "tribunal",
            "case_family",
            "case_number",
            "hearing_date",
            "transcript_url",
            "video_url",
            "transcript_readable",
            "witness_name_or_code",
            "witness_identity_status",
            "witness_resolution_confidence",
            "examination_types_present",
            "transcript_speaker_turns",
            "witness_utterance_count",
            "counsel_utterance_count",
            "judge_utterance_count",
            "testimony_start_page",
            "testimony_end_page",
            "testimony_start_marker",
            "testimony_end_marker",
            "estimated_testimony_minutes",
            "contains_actual_witness_testimony",
            "non_witness_hearing_reason",
            "transcript_language",
            "video_language",
            "notes",
            "witness_key",
            "is_repeat_witness",
            "witness_hearing_count",
            "cumulative_witness_utterances",
            "cumulative_estimated_testimony_minutes",
            "raw_witness_utterance_count",
            "usable_witness_utterance_estimate",
            "short_response_count",
            "question_utterance_count",
            "answer_utterance_count",
            "question_answer_pair_count",
        ],
    )

    summary = {
        "paired_hearings_scanned": paired_scanned,
        "readable_transcripts": len(readable_hearings),
        "hearings_with_witness_testimony": len(hearing_ids_with_testimony),
        "non_witness_hearings": len(non_witness_hearing_ids),
        "public_witnesses_discovered": len(public_witnesses),
        "protected_witnesses_discovered": len(protected_witnesses),
        "distinct_witnesses_discovered": len(distinct_witnesses),
        "repeat_witness_hearings": len(hearing_ids_with_repeat),
        "unresolved_witness_hearings": len(unresolved_hearing_ids),
        "raw_witness_utterances": raw_witness_utterances,
        "usable_witness_utterances_estimated": usable_witness_utterances,
        "candidate_testimony_hours": round(candidate_minutes / 60.0, 2),
        "selected_hearings": 0,
        "selected_distinct_witnesses": 0,
        "selected_estimated_hours": 0.0,
        "selected_estimated_utterances": 0,
        "case_families_selected": 0,
        "target_hours_status": "pending_selection",
        "target_witnesses_status": "pending_selection",
        "target_utterances_status": "pending_selection",
    }
    ensure_dir(Path("reports/phase2"))
    Path("reports/phase2/paired_hearing_witness_discovery_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote {len(out_rows)} discovery rows to {args.output_csv}")
    print("Wrote discovery summary to reports/phase2/paired_hearing_witness_discovery_summary.json")


if __name__ == "__main__":
    main()
