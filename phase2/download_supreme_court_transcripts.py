from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .common import download_file, ensure_dir, extract_text_from_file, safe_filename, sha1_short, slugify, write_csv


DEFAULT_PAGE_URL = "https://www.supremecourt.gov/oral_arguments/availabilityoforalargumenttranscripts.aspx"


def discover_links(page_url: str, *, include_all: bool = False) -> list[dict[str, str]]:
    response = requests.get(page_url, timeout=60)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor["href"])
        text = " ".join(anchor.stripped_strings).strip()
        href_lower = href.lower()
        text_lower = text.lower()
        if not include_all and not (
            "transcript" in href_lower
            or "transcript" in text_lower
            or href_lower.endswith((".pdf", ".html", ".htm", ".txt"))
        ):
            continue
        if href in seen:
            continue
        seen.add(href)
        rows.append({"title": text or Path(href).name, "url": href})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Supreme Court oral argument transcripts")
    parser.add_argument("--output", type=str, default="data/phase2/scotus", help="Output directory")
    parser.add_argument("--page-url", type=str, default=DEFAULT_PAGE_URL, help="Official transcript listing page")
    parser.add_argument("--max-links", type=int, default=0, help="Optional cap on the number of discovered links")
    parser.add_argument("--include-all-links", action="store_true", help="Keep every link from the page instead of filtering to transcript-like links")
    args = parser.parse_args()

    out = Path(args.output)
    raw_dir = ensure_dir(out / "raw")
    text_dir = ensure_dir(out / "text")
    index_dir = ensure_dir(out / "index")

    links = discover_links(args.page_url, include_all=args.include_all_links)
    if args.max_links > 0:
        links = links[: args.max_links]

    rows: list[dict[str, object]] = []
    for idx, entry in enumerate(links, start=1):
        title = entry["title"].strip()
        url = entry["url"].strip()
        fallback = safe_filename(url, f"scotus_{idx}")
        stem = slugify(title or fallback)
        sample_id = f"scotus_{sha1_short(url)}_{stem[:32]}"
        dest = raw_dir / fallback
        try:
            if not dest.exists():
                download_file(url, dest)
            transcript_text = extract_text_from_file(dest)
        except Exception as exc:
            transcript_text = ""
            print(f"Skipped {url}: {exc}")
            continue

        text_path = text_dir / f"{sample_id}.txt"
        text_path.write_text(transcript_text, encoding="utf-8")
        rows.append(
            {
                "sample_id": sample_id,
                "case_id": sample_id,
                "court": "US_Supreme_Court",
                "source_type": "oral_argument_transcript",
                "language": "en",
                "split_hint": "unsplit",
                "title": title,
                "source_url": url,
                "raw_path": str(dest),
                "text_path": str(text_path),
                "transcript": transcript_text,
                "audio_path": "",
                "video_path": "",
                "notes": "Public transcript for legal-domain text adaptation; not all files provide audio/video.",
            }
        )

    index_csv = index_dir / "scotus_transcripts.csv"
    write_csv(
        index_csv,
        rows,
        [
            "sample_id",
            "case_id",
            "court",
            "source_type",
            "language",
            "split_hint",
            "title",
            "source_url",
            "raw_path",
            "text_path",
            "transcript",
            "audio_path",
            "video_path",
            "notes",
        ],
    )
    print(f"Wrote {len(rows)} Supreme Court transcript rows to {index_csv}")


if __name__ == "__main__":
    main()

