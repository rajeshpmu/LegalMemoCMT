from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


def _extract_case_number(url: str, title: str) -> str:
    url_tail = url.rstrip("/").split("/")[-1]
    candidate = url_tail.replace("%2F", "/").replace("%2f", "/")
    if re.match(r"^[A-Z]{1,6}-[0-9A-Z-]+(?:/[0-9A-Z-]+)?$", candidate, re.I):
        return candidate
    title_match = re.search(r"\(([A-Z0-9-]+(?:/[A-Z0-9-]+)?)\)", title)
    if title_match:
        return title_match.group(1)
    return candidate


def _extract_case_family(title: str, case_number: str) -> str:
    cleaned = title.strip()
    if case_number:
        cleaned = cleaned.replace(f"({case_number})", "").strip(" -")
    return cleaned or case_number


def _extract_sections(soup: BeautifulSoup) -> tuple[bool, bool, bool]:
    text = soup.get_text(" ", strip=True).lower()
    return ("transcripts" in text, "court recordings" in text, "videos" in text)


def _infer_tribunal(case_number: str, page_url: str) -> str:
    case_number = case_number.upper()
    if case_number.startswith("IT-"):
        return "ICTY"
    if case_number.startswith("ICTR-"):
        return "ICTR"
    if case_number.startswith("MICT-"):
        return "IRMCT"
    if "irmct" in page_url.lower():
        return "IRMCT"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl official UCR case pages and extract candidate ledger rows")
    parser.add_argument("--seed-csv", default="data/phase2/source_manifests/official_ucr_case_seeds.csv", help="CSV with case_page_url seeds")
    parser.add_argument("--output-csv", default="data/phase2/source_manifests/official_ucr_case_candidates.csv", help="Output candidate ledger CSV")
    parser.add_argument("--limit", type=int, default=0, help="Optional seed row limit")
    args = parser.parse_args()

    seeds = read_csv_rows(Path(args.seed_csv))
    if args.limit and args.limit > 0:
        seeds = seeds[: args.limit]

    out_rows: list[dict[str, object]] = []
    for idx, seed in enumerate(seeds, start=1):
        page_url = (seed.get("case_page_url") or "").strip()
        notes = (seed.get("notes") or "").strip()
        if not page_url:
            continue
        try:
            resp = requests.get(page_url, timeout=60, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            heading = soup.find(["h1", "h2"])
            if heading and heading.get_text(" ", strip=True):
                title = heading.get_text(" ", strip=True)
            case_number = _extract_case_number(page_url, title)
            case_family = _extract_case_family(title, case_number)
            has_transcripts, has_court_recordings, has_videos = _extract_sections(soup)
            tribunal = _infer_tribunal(case_number, page_url)
            out_rows.append(
                {
                    "tribunal": tribunal,
                    "case_family": case_family,
                    "case_number": case_number,
                    "candidate_priority": "AUTO_CRAWLED",
                    "has_video": "YES" if has_videos else "UNKNOWN",
                    "tap_count": "UNKNOWN",
                    "estimated_hours": "UNKNOWN",
                    "estimated_witnesses": "UNKNOWN",
                    "source_url": page_url,
                    "inventory_search_url": page_url,
                    "curation_action": "Review official UCR case page and validate recording volume.",
                    "include_in_tri_modal_set": "YES_AFTER_LINK_VALIDATION" if has_videos or has_court_recordings else "NO",
                    "notes": f"Auto-crawled from official UCR page. transcripts={has_transcripts}; recordings={has_court_recordings}; videos={has_videos}. {notes}",
                }
            )
            print(
                f"row={idx} case_family={case_family!r} case_number={case_number!r} "
                f"tribunal={tribunal!r} videos={has_videos} recordings={has_court_recordings}"
            )
        except Exception as exc:
            out_rows.append(
                {
                    "tribunal": "",
                    "case_family": "",
                    "case_number": "",
                    "candidate_priority": "AUTO_CRAWLED_ERROR",
                    "has_video": "UNKNOWN",
                    "tap_count": "UNKNOWN",
                    "estimated_hours": "UNKNOWN",
                    "estimated_witnesses": "UNKNOWN",
                    "source_url": page_url,
                    "inventory_search_url": page_url,
                    "curation_action": "Fix crawl error and retry.",
                    "include_in_tri_modal_set": "NO",
                    "notes": f"crawl_error={exc}",
                }
            )
            print(f"row={idx} ERROR {page_url}: {exc}")

    ensure_dir(Path(args.output_csv).parent)
    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "tribunal",
            "case_family",
            "case_number",
            "candidate_priority",
            "has_video",
            "tap_count",
            "estimated_hours",
            "estimated_witnesses",
            "source_url",
            "inventory_search_url",
            "curation_action",
            "include_in_tri_modal_set",
            "notes",
        ],
    )
    print(f"Wrote {len(out_rows)} official UCR candidate rows to {args.output_csv}")


if __name__ == "__main__":
    main()
