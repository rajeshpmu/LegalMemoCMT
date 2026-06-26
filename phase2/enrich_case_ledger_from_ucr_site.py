from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


UCR_BASE = "https://ucr.irmct.org"


def _normalize_case_number(case_number: str) -> str:
    case_number = (case_number or "").strip()
    if not case_number:
        return ""
    case_number = re.sub(r"\s*/\s*", "/", case_number)
    case_number = re.sub(r"\s*-\s*", "-", case_number)
    return case_number


def _case_page_url(case_number: str) -> str:
    encoded = quote(case_number, safe="")
    return f"{UCR_BASE}/scasedocs/case/{encoded}"


def _fetch_page(url: str) -> requests.Response:
    resp = requests.get(url, timeout=60, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True)
    resp.raise_for_status()
    return resp


def _has_section(soup: BeautifulSoup, labels: list[str]) -> bool:
    text = soup.get_text(" ", strip=True).lower()
    return any(label.lower() in text for label in labels)


def _extract_page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.text.strip():
        return soup.title.text.strip()
    heading = soup.find(["h1", "h2"])
    return heading.get_text(" ", strip=True) if heading else ""


def _load_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        rows.extend(read_csv_rows(path))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich the Phase 2 case ledger by checking official UCR case pages")
    parser.add_argument("--ledger-csv", default="data/phase2/source_manifests/case_candidate_ledger.csv", help="Primary input case ledger CSV")
    parser.add_argument(
        "--extra-ledger-csv",
        action="append",
        default=[],
        help="Additional ledger CSVs to append before enrichment; may be repeated",
    )
    parser.add_argument("--output-csv", default="data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv", help="Output enriched CSV")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit")
    args = parser.parse_args()

    input_paths = [Path(args.ledger_csv), *[Path(p) for p in args.extra_ledger_csv]]
    rows = _load_rows(input_paths)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    out_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=1):
        case_number_raw = _normalize_case_number(str(row.get("case_number") or ""))
        tribunal = (row.get("tribunal") or "").strip()
        case_family = (row.get("case_family") or "").strip()
        case_page = ""
        status = "missing_case_number"
        page_title = ""
        has_transcripts = False
        has_court_recordings = False
        has_videos = False
        link_count = 0
        error_message = ""

        if case_number_raw and "tbd" not in case_number_raw.lower() and "manual" not in case_number_raw.lower():
            normalized_case_number = case_number_raw.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
            case_page = _case_page_url(normalized_case_number.replace("-T", ""))
            try:
                resp = _fetch_page(case_page)
                soup = BeautifulSoup(resp.text, "html.parser")
                page_title = _extract_page_title(soup)
                has_transcripts = _has_section(soup, ["transcripts"])
                has_court_recordings = _has_section(soup, ["court recordings"])
                has_videos = _has_section(soup, ["videos"])
                link_count = len(soup.find_all("a", href=True))
                status = "ok"
            except Exception as exc:
                status = "error"
                error_message = str(exc)
        else:
            error_message = "case number missing or placeholder"

        out_rows.append(
            {
                "enriched_id": f"{tribunal.lower()}_{idx:03d}",
                "tribunal": tribunal,
                "case_family": case_family,
                "case_number": case_number_raw,
                "official_case_page": case_page,
                "page_title": page_title,
                "has_transcripts": "yes" if has_transcripts else "no",
                "has_court_recordings": "yes" if has_court_recordings else "no",
                "has_videos": "yes" if has_videos else "no",
                "link_count": link_count,
                "status": status,
                "error_message": error_message,
                "notes": row.get("notes", ""),
            }
        )
        print(
            f"row={idx} case_name={case_family!r} case_number={case_number_raw or '(none)'} "
            f"videos={has_videos} recordings={has_court_recordings} status={status}"
        )

    ensure_dir(Path(args.output_csv).parent)
    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "enriched_id",
            "tribunal",
            "case_family",
            "case_number",
            "official_case_page",
            "page_title",
            "has_transcripts",
            "has_court_recordings",
            "has_videos",
            "link_count",
            "status",
            "error_message",
            "notes",
        ],
    )
    print(f"Wrote {len(out_rows)} enriched ledger rows to {args.output_csv}")


if __name__ == "__main__":
    main()
