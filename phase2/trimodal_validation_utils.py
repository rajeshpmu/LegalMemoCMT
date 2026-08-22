from __future__ import annotations

import csv
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests

try:
    import imageio_ffmpeg
except Exception:  # pragma: no cover
    imageio_ffmpeg = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment]

try:
    from .common import ensure_dir, read_csv_rows, write_csv, sha1_short
except Exception:  # pragma: no cover
    from phase2.common import ensure_dir, read_csv_rows, write_csv, sha1_short  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / "data" / "phase2" / "trimodal_validation_cache"
HEARING_INPUT = ROOT / "data" / "processed" / "phase2" / "hearing_manifest.csv"
WITNESS_INPUT = ROOT / "data" / "phase2" / "source_manifests" / "witness_harvest_manifest_resolved.csv"
HEARING_VALIDATED = ROOT / "data" / "processed" / "phase2" / "hearing_manifest_validated.csv"
WITNESS_VALIDATED = ROOT / "data" / "processed" / "phase2" / "witness_manifest_validated.csv"
SUMMARY_OUTPUT = ROOT / "reports" / "phase2" / "trimodal_validation_summary.json"
PILOT_PAIRED_COUNT = 6
EXTRA_TRANSCRIPT_ROWS = 5

NO_WITNESS_TERMS = {
    "appeal",
    "judgment",
    "judgement",
    "order",
    "status conference",
    "motion hearing",
    "closing brief",
    "closing arguments",
    "final brief",
    "sentencing",
    "oral argument",
    "submissions",
    "procedural",
    "decision",
}

TESTIMONY_TITLE_HINTS = {
    "hearing",
    "session",
    "transcript",
    "witness",
    "testimony",
    "examination",
    "cross-examination",
    "cross examination",
    "re-examination",
    "reexamination",
    "direct examination",
    "questioning",
}

PROCEEDINGS_MARKERS = (
    "P R O C E E D I N G S",
    "PROCEEDINGS",
)

WITNESS_SECTION_RE = re.compile(r"^\s*WITNESS(?:ES)?\b", re.I)
WITNESS_HEADING_RE = re.compile(r"^\s*(?:THE\s+)?WITNESS\b[:\-]?\s*(.*)$", re.I)
EXAM_HEADING_RE = re.compile(
    r"(?:examination[- ]in[- ]chief|cross[- ]examination|re[- ]?examination|re[- ]?direct|recross|court questioning|questions from the bench|questioning by the judges)",
    re.I,
)

WITNESS_PATTERNS = [
    re.compile(r"^\s*(?:WITNESS|THE WITNESS)\s+([A-Z]{1,4}\d{0,4}|[A-Z]{2,4})\b", re.I | re.M),
]

SPEAKER_LABEL_RE = re.compile(r"^(?P<label>[A-Z][A-Z0-9 .,'()\/\-]{1,60})\s*:\s*(?P<text>.*)$")
QA_RE = re.compile(r"^(?P<label>[QA])\s*[:.]\s*(?P<text>.*)$", re.I)
DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<year>\d{4})\b",
    re.I,
)
DATE_RE_ALT = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\b",
    re.I,
)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".webm"}
TEXT_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt", ".html", ".htm", ".tif", ".tiff"}


@dataclass
class MediaProbe:
    status: str
    duration_seconds: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    video_playable: bool = False
    audio_present: bool = False
    resolution: str = ""
    frame_rate: str = ""
    stderr: str = ""


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_case_number(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return text


def _clean_transcript_line(line: str) -> str:
    text = normalize_text(line)
    if not text:
        return ""
    text = re.sub(r"^\s*\d{1,5}\s+", "", text)
    text = re.sub(r"^\s*page\s+\d+\s*", "", text, flags=re.I)
    return normalize_text(text)


def has_testimony_signal(text: str) -> bool:
    lowered = normalize_text(text).lower()
    if not lowered:
        return False
    if any(term in lowered for term in NO_WITNESS_TERMS):
        return False
    return any(term in lowered for term in TESTIMONY_TITLE_HINTS)


def csv_rows(path: str | Path) -> list[dict[str, str]]:
    return read_csv_rows(Path(path))


def csv_write(path: str | Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    write_csv(Path(path), list(rows), fieldnames)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_cache_dir(*parts: str) -> Path:
    return ensure_dir(CACHE_ROOT.joinpath(*parts))


def select_pilot_rows(hearing_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    paired = [
        row
        for row in hearing_rows
        if normalize_text(row.get("pairing_status")) == "paired"
        and normalize_text(row.get("video_url"))
        and normalize_text(row.get("transcript_url"))
    ]
    paired.sort(key=lambda row: (
        0 if has_testimony_signal(normalize_text(row.get("record_title"))) else 1,
        int(float(row.get("expected_duration_minutes") or 0) or 0),
        normalize_case_number(row.get("case_number")),
        normalize_text(row.get("hearing_date")),
        normalize_text(row.get("record_title")),
    ))

    by_case: dict[str, list[dict[str, str]]] = {}
    for row in paired:
        by_case.setdefault(normalize_case_number(row.get("case_number")), []).append(row)

    selected: list[dict[str, str]] = []
    used: set[str] = set()
    case_order = sorted(by_case)
    while len(selected) < PILOT_PAIRED_COUNT and any(by_case.values()):
        progressed = False
        for case_number in case_order:
            bucket = by_case.get(case_number, [])
            if not bucket:
                continue
            row = bucket.pop(0)
            hearing_id = normalize_text(row.get("hearing_id"))
            if hearing_id in used:
                continue
            selected.append(row)
            used.add(hearing_id)
            progressed = True
            if len(selected) >= PILOT_PAIRED_COUNT:
                break
        if not progressed:
            break

    transcript_only_cases = ["IT-05-88", "IT-09-92", "IT-04-81"]
    transcript_rows = [
        row
        for row in hearing_rows
        if normalize_text(row.get("pairing_status")) == "transcript_only"
        and normalize_text(row.get("transcript_verified")).upper() == "YES"
        and normalize_case_number(row.get("case_number")) in transcript_only_cases
    ]
    transcript_rows.sort(key=lambda row: (
        normalize_case_number(row.get("case_number")),
        normalize_text(row.get("hearing_date")),
        normalize_text(row.get("record_title")),
    ))
    seen_cases = {normalize_case_number(row.get("case_number")) for row in selected}
    while len(selected) < PILOT_PAIRED_COUNT + EXTRA_TRANSCRIPT_ROWS:
        progressed = False
        for case_number in transcript_only_cases:
            for row in transcript_rows:
                if normalize_case_number(row.get("case_number")) != case_number:
                    continue
                hearing_id = normalize_text(row.get("hearing_id"))
                if hearing_id in used:
                    continue
                selected.append(row)
                used.add(hearing_id)
                seen_cases.add(case_number)
                progressed = True
                if len(selected) >= PILOT_PAIRED_COUNT + EXTRA_TRANSCRIPT_ROWS:
                    break
                break
            if len(selected) >= PILOT_PAIRED_COUNT + EXTRA_TRANSCRIPT_ROWS:
                break
        if not progressed:
            break

    return selected


def download_file(url: str, dest: Path, *, timeout: int = 90) -> Path:
    ensure_dir(dest.parent)
    headers = {"User-Agent": "LegalMemoCMT-Phase2/1.0"}
    with requests.get(url, headers=headers, timeout=timeout, stream=True, verify=True) as resp:
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").lower()
        if "text/html" in content_type or "application/xhtml+xml" in content_type:
            raise ValueError(f"refusing html response for {url}")
        with dest.open("wb") as out:
            first = True
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                if first:
                    first = False
                    head = chunk.lstrip().lower()
                    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
                        raise ValueError(f"refusing html payload for {url}")
                out.write(chunk)
    return dest


def ffmpeg_exe() -> str:
    if imageio_ffmpeg is None:
        raise RuntimeError("imageio-ffmpeg is not available")
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_media_url(url: str, *, timeout: int = 90) -> MediaProbe:
    if not url:
        return MediaProbe(status="missing_url")
    if imageio_ffmpeg is None:
        return MediaProbe(status="ffmpeg_unavailable")
    exe = ffmpeg_exe()
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-i", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return MediaProbe(status="probe_timeout")

    stderr = proc.stderr or ""
    duration = 0.0
    video_codec = ""
    audio_codec = ""
    resolution = ""
    frame_rate = ""
    video_playable = False
    audio_present = False

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

    for line in stderr.splitlines():
        if "Stream #" not in line:
            continue
        if "Video:" in line and not video_codec:
            vm = re.search(r"Video:\s*([^,(]+)", line)
            if vm:
                video_codec = vm.group(1).strip()
            rm = re.search(r"(\d{2,5})x(\d{2,5})", line)
            if rm:
                resolution = f"{rm.group(1)}x{rm.group(2)}"
            fm = re.search(r"(\d+(?:\.\d+)?)\s*fps", line)
            if fm:
                frame_rate = fm.group(1)
            video_playable = True
        elif "Audio:" in line and not audio_codec:
            am = re.search(r"Audio:\s*([^,(]+)", line)
            if am:
                audio_codec = am.group(1).strip()
            audio_present = True
        elif "Audio:" in line:
            audio_present = True

    status = "validated" if duration > 0 and video_playable and audio_present else "invalid_media"
    if "html" in stderr.lower():
        status = "html_response"
    return MediaProbe(
        status=status,
        duration_seconds=duration,
        video_codec=video_codec,
        audio_codec=audio_codec,
        video_playable=video_playable,
        audio_present=audio_present,
        resolution=resolution,
        frame_rate=frame_rate,
        stderr=stderr,
    )


def _textutil_extract(path: Path, tmp_dir: Path) -> tuple[str, int]:
    out = tmp_dir / f"{path.stem}.txt"
    subprocess.run(["textutil", "-convert", "txt", "-output", str(out), str(path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = out.read_text(encoding="utf-8", errors="ignore")
    page_count = max(1, text.count("\f") + 1) if text.strip() else 0
    return text, page_count


def extract_transcript_text(path: Path) -> tuple[str, int]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError("pypdf is not available")
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text.strip(), len(reader.pages)
    if suffix in {".doc", ".docx", ".rtf"}:
        return _textutil_extract(path, path.parent)
    if suffix in {".html", ".htm"}:
        if BeautifulSoup is None:
            return path.read_text(encoding="utf-8", errors="ignore"), 0
        html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
        return text.strip(), max(1, text.count("\f") + 1) if text.strip() else 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text.strip(), max(1, text.count("\f") + 1) if text.strip() else 0


def transcript_url_to_local(url: str, manifest_id: str, *, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or ensure_cache_dir("transcripts")
    suffix = Path(urlparse(url).path).suffix.lower() or ".txt"
    if suffix not in TEXT_EXTENSIONS:
        suffix = ".txt"
    return out_dir / f"{manifest_id}{suffix}"


def maybe_download_transcript(url: str, manifest_id: str, *, output_dir: Path | None = None) -> Path:
    dest = transcript_url_to_local(url, manifest_id, output_dir=output_dir)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    return download_file(url, dest)


def transcript_header_date(text: str) -> str:
    for line in text.splitlines()[:120]:
        line = normalize_text(line)
        if not line:
            continue
        m = DATE_RE.search(line) or DATE_RE_ALT.search(line)
        if m:
            month = m.group("month")
            day = int(m.group("day"))
            year = int(m.group("year"))
            month_map = {
                "january": 1,
                "february": 2,
                "march": 3,
                "april": 4,
                "may": 5,
                "june": 6,
                "july": 7,
                "august": 8,
                "september": 9,
                "october": 10,
                "november": 11,
                "december": 12,
            }
            return f"{day:02d}/{month_map[month.lower()]:02d}/{year:04d}"
    return ""


def detect_speaker_labels(text: str) -> list[str]:
    text = _transcript_body(text)
    labels: list[str] = []
    for line in text.splitlines():
        stripped = _clean_transcript_line(line)
        if not stripped:
            continue
        m = SPEAKER_LABEL_RE.match(stripped)
        if m:
            label = normalize_text(m.group("label"))
            if label and label not in labels:
                labels.append(label)
            continue
        q = QA_RE.match(stripped)
        if q:
            label = normalize_text(q.group("label")).upper()
            if label and label not in labels:
                labels.append(label)
    return labels


def classify_speaker(label: str) -> str:
    up = normalize_text(label).upper()
    if up in {"JUDGE", "THE COURT", "PRESIDING JUDGE", "MR PRESIDENT", "MRS. JUSTICE", "MS. JUSTICE"} or "JUDGE" in up or "PRESIDENT" in up:
        return "judge"
    if up in {"Q", "QUESTION"} or "QUESTION" in up:
        return "counsel"
    if up in {"A", "ANSWER"}:
        return "witness"
    if "WITNESS" in up:
        return "witness"
    if any(term in up for term in ["PROSECUTOR", "DEFENCE", "DEFENSE", "COUNSEL", "MR.", "MS.", "MRS."]):
        return "counsel"
    return "counsel"


def _transcript_body(text: str) -> str:
    upper = text.upper()
    positions = [upper.find(marker) for marker in PROCEEDINGS_MARKERS if upper.find(marker) >= 0]
    if not positions:
        return text
    return text[min(positions) :]


def _transcript_front_matter(text: str) -> str:
    upper = text.upper()
    positions = [upper.find(marker) for marker in PROCEEDINGS_MARKERS if upper.find(marker) >= 0]
    if not positions:
        return text
    return text[: min(positions)]


def has_witness_testimony(text: str) -> bool:
    body = _transcript_body(text)
    cleaned_body = "\n".join(_clean_transcript_line(line) for line in body.splitlines())
    if EXAM_HEADING_RE.search(cleaned_body):
        return True
    if re.search(r"(?im)^\s*(?:THE\s+)?WITNESS\s*[:\-]", cleaned_body):
        return True
    if re.search(r"(?im)^\s*[QA]\s*[:.]\s*\S", cleaned_body):
        return True
    return False


def _clean_identity_line(line: str) -> str:
    text = normalize_text(line)
    text = re.sub(r"\((?:continued|commenced[^)]*|closed session[^)]*)\)", "", text, flags=re.I)
    text = re.sub(r"\b(?:continued|continued\.)$", "", text, flags=re.I)
    return normalize_text(text)


def _looks_like_protected_code(candidate: str) -> bool:
    candidate = normalize_text(candidate)
    return bool(re.fullmatch(r"[A-Z]{1,4}\d{0,4}", candidate) or re.fullmatch(r"[A-Z]{2,4}", candidate))


def _looks_like_public_name(candidate: str) -> bool:
    candidate = normalize_text(candidate)
    if not candidate:
        return False
    if any(token in candidate.lower() for token in ["for the defence", "for the defense", "for the prosecution", "the witness"]):
        return False
    if any(ch.isdigit() for ch in candidate):
        return False
    if len(candidate.split()) < 2:
        return False
    if len(candidate.split()) > 6:
        return False
    return bool(re.fullmatch(r"[A-Za-zÀ-ÿ'’\-.]+(?:\s+[A-Za-zÀ-ÿ'’\-.]+){1,5}", candidate))


def _index_lines(text: str) -> list[str]:
    front = _transcript_front_matter(text)
    lines: list[str] = []
    for raw in front.splitlines():
        line = _clean_transcript_line(raw)
        if line:
            lines.append(line)
    return lines


def count_utterances(text: str) -> dict[str, int]:
    lines = [_clean_transcript_line(line) for line in _transcript_body(text).splitlines()]
    utterances: list[tuple[str, str]] = []
    current_label = ""
    current_text: list[str] = []

    def flush() -> None:
        nonlocal current_label, current_text
        joined = normalize_text(" ".join(current_text))
        if joined:
            utterances.append((current_label or "UNKNOWN", joined))
        current_label = ""
        current_text = []

    for line in lines:
        if not line:
            continue
        if re.fullmatch(r"[IVXLC]+\.*", line):
            continue
        if line.upper().startswith("PAGE ") or line.upper().startswith("PAGE"):
            continue
        m = SPEAKER_LABEL_RE.match(line)
        if m:
            flush()
            current_label = normalize_text(m.group("label"))
            remainder = normalize_text(m.group("text"))
            if remainder:
                current_text.append(remainder)
            continue
        q = QA_RE.match(line)
        if q:
            flush()
            current_label = "Q" if q.group("label").upper() == "Q" else "A"
            remainder = normalize_text(q.group("text"))
            if remainder:
                current_text.append(remainder)
            continue
        if current_label:
            current_text.append(line)
        elif len(line) > 2:
            current_label = "UNKNOWN"
            current_text.append(line)

    flush()

    counts = {"total": len(utterances), "witness": 0, "counsel": 0, "judge": 0}
    for label, _text in utterances:
        role = classify_speaker(label)
        counts[role] += 1
    return counts


def detect_examination_type(text: str) -> str:
    lowered = _transcript_body(text).lower()
    hits = []
    if "direct examination" in lowered or "examination-in-chief" in lowered:
        hits.append("direct_examination")
    if "cross-examination" in lowered or "cross examination" in lowered:
        hits.append("cross_examination")
    if "redirect" in lowered or "re-direct" in lowered:
        hits.append("redirect_examination")
    if "recross" in lowered:
        hits.append("recross_examination")
    if any(term in lowered for term in ["questions from the bench", "questioning by the judges", "court questioning", "judge"]):
        hits.append("court_questioning")
    if not hits:
        return "unknown"
    if len(set(hits)) > 1:
        return "mixed"
    return hits[0]


def extract_witness_identity(text: str, title: str = "") -> tuple[str, str, str, str]:
    title_text = normalize_text(title)
    if any(term in title_text.lower() for term in NO_WITNESS_TERMS) and not has_witness_testimony(text):
        return "NO_WITNESS_TESTIMONY", "NO_WITNESS_TESTIMONY", "title heuristic", "high"

    lines = _index_lines(text)
    seen_witness_marker = False
    for line in lines:
        clean = _clean_identity_line(line)
        if not clean:
            continue
        if WITNESS_SECTION_RE.match(clean):
            seen_witness_marker = True
            m = re.match(r"^\s*(?:WITNESS|THE WITNESS)\s+(.+)$", clean, re.I)
            if m:
                candidate = _clean_identity_line(m.group(1))
                if _looks_like_protected_code(candidate):
                    return candidate, "PROTECTED_CODE", "index heading", "high"
                if _looks_like_public_name(candidate):
                    return candidate, "PUBLIC_NAME", "index heading", "high"
            continue
        if EXAM_HEADING_RE.search(clean):
            break
        candidate = clean
        if candidate.upper() in {"WITNESS", "WITNESSES"}:
            seen_witness_marker = True
            continue
        if _looks_like_protected_code(candidate):
            return candidate, "PROTECTED_CODE", "index body", "high"
        if _looks_like_public_name(candidate) and seen_witness_marker:
            return candidate, "PUBLIC_NAME", "index body", "medium"

    body = _transcript_body(text)
    if has_witness_testimony(body):
        return "UNRESOLVED_WITNESS", "UNRESOLVED_WITNESS", "transcript body", "low"
    return "NO_WITNESS_TESTIMONY", "NO_WITNESS_TESTIMONY", "title/body heuristic", "medium"


def normalize_date_string(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return text
