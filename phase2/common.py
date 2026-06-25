from __future__ import annotations

import csv
import hashlib
import re
import ssl
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

import requests

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment]


USER_AGENT = "LegalMemoCMT-Phase2/1.0 (+local research pipeline)"


def slugify(text: str, *, max_length: int = 80) -> str:
    text = unescape(text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:max_length].strip("-") or "item"


def safe_filename(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if name:
        return name
    return fallback


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_file(url: str, dest: Path, *, timeout: int = 60) -> Path:
    ensure_dir(dest.parent)
    headers = {"User-Agent": USER_AGENT}
    with requests.get(url, headers=headers, timeout=timeout, stream=True, verify=True) as response:
        response.raise_for_status()
        with dest.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    out.write(chunk)
    return dest


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text_from_pdf(path: Path) -> str:
    if PdfReader is None:
        raise ImportError("pypdf is required to extract text from PDF files")
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n".join(pages).strip()


def extract_text_from_html(path: Path) -> str:
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 is required to extract text from HTML files")
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    text = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix in {".html", ".htm"}:
        return extract_text_from_html(path)
    return read_text_file(path)


def write_csv(path: Path, rows: Sequence[dict[str, object]], fieldnames: Sequence[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    import pandas as pd

    df = pd.read_csv(path)
    return [{str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()} for _, row in df.iterrows()]


def group_case_splits(case_ids: Sequence[str], *, train_ratio: float, dev_ratio: float, test_ratio: float, seed: int = 42) -> dict[str, str]:
    import random

    if not case_ids:
        return {}
    if abs((train_ratio + dev_ratio + test_ratio) - 1.0) > 1e-6:
        raise ValueError("Split ratios must sum to 1.0")
    rng = random.Random(seed)
    unique = sorted(set(case_ids))
    rng.shuffle(unique)
    n = len(unique)
    train_end = max(int(n * train_ratio), 1)
    dev_end = min(max(train_end + int(n * dev_ratio), train_end + 1), n)
    train_cases = set(unique[:train_end])
    dev_cases = set(unique[train_end:dev_end])
    test_cases = set(unique[dev_end:]) if dev_end < n else set()
    if not test_cases and unique:
        test_cases = {unique[-1]}
        train_cases.discard(unique[-1])
        dev_cases.discard(unique[-1])
    mapping: dict[str, str] = {}
    for case_id in unique:
        if case_id in train_cases:
            mapping[case_id] = "train"
        elif case_id in dev_cases:
            mapping[case_id] = "dev"
        else:
            mapping[case_id] = "test"
    return mapping


def sha1_short(text: str, length: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:length]

