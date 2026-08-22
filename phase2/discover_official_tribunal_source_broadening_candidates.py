from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


OFFICIAL_CASE_LISTS = {
    "ICTR": "https://unictr.irmct.org/en/cases",
    "ICTY": "https://www.icty.org/en/cases",
    "IRMCT": "https://www.irmct.org/en/cases",
}
DEFAULT_SOURCE_MANIFEST = Path("data/phase2/source_manifests/tribunal_sources_target_dataset.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/tribunal_source_broadening_review.csv")
DEFAULT_SUMMARY = Path("reports/phase2/tribunal_source_broadening_review_summary.json")

MANUAL_CURATION_OVERRIDES = {
    "perisic trial": {
        "candidate_priority": "MEDIUM",
        "has_video": "UNKNOWN_VERIFY_IN_UCR",
        "tap_count": "UNKNOWN",
        "estimated_hours": "0-10",
        "estimated_witnesses": "5-15 possible",
        "curation_action": "Treat as transcript-only until an actual hearing-level recording is verified.",
        "include_in_tri_modal_set": "ONLY_IF_VIDEO_LINKS_RESOLVED",
        "recommended_action": "hold_for_link_validation",
        "recommended_score": 120,
        "content_type": "Transcript-only",
        "manual_selection": "NO",
        "notes": "Manual curation override: transcript-only bootstrap candidate; do not promote as witness-video material without hearing-level validation.",
    }
}

CASE_NUMBER_RE = re.compile(r"\b([A-Z]{1,6}-[0-9A-Z]+(?:-[0-9A-Z]+)*(?:/[0-9A-Z]+)?)\b", re.I)
STATUS_TOKENS = {
    "completed": "COMPLETED",
    "ongoing": "ONGOING",
    "transferred": "TRANSFERRED",
    "fugitive": "FUGITIVE",
    "contumacy": "CONTUMACY",
    "contempt": "CONTEMPT",
    "appeal": "APPEAL",
}


@dataclass
class CaseEntry:
    tribunal: str
    case_family: str
    case_number: str
    case_status: str
    case_page_url: str
    page_url: str
    accused_names: str = ""


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def _case_link(tribunal: str, href: str) -> bool:
    href = href.lower()
    if href.startswith("#") or ".pdf" in href or "case information sheet" in href or "pressrel" in href or "custom7" in href:
        return False
    if tribunal == "ICTR":
        return "/en/cases/" in href and not href.endswith("/cases")
    if tribunal == "ICTY":
        return "/en/case/" in href
    if tribunal == "IRMCT":
        return "/en/cases/" in href and not href.endswith("/cases")
    return False


def _extract_case_number(text: str) -> str:
    match = CASE_NUMBER_RE.search(text or "")
    return match.group(1).upper() if match else ""


def _extract_case_family(text: str, case_number: str) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return ""
    if case_number:
        cleaned = cleaned.replace(f"({case_number})", "")
        cleaned = cleaned.replace(f"({case_number.lower()})", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -;,")
    return cleaned


def _status_from_text(text: str) -> str:
    lower = _norm(text)
    for token, normalized in STATUS_TOKENS.items():
        if token in lower:
            return normalized
    return ""


def _parse_case_list_page(tribunal: str, page_url: str) -> list[CaseEntry]:
    resp = requests.get(page_url, timeout=60, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    entries: list[CaseEntry] = []
    seen: set[tuple[str, str]] = set()

    if tribunal == "ICTR":
        for tr in soup.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            links = [a for a in tr.find_all("a", href=True) if _case_link(tribunal, a["href"])]
            if not links:
                continue
            case_link = links[0]
            case_text = _clean(case_link.get_text(" ", strip=True))
            row_text = _clean(tr.get_text(" ", strip=True))
            case_number = _extract_case_number(row_text) or _extract_case_number(case_text)
            if not case_number:
                continue
            case_family = _extract_case_family(case_text or row_text, case_number)
            case_status = _status_from_text(row_text)
            accused_names = ""
            if len(cells) >= 4:
                accused_names = _clean(cells[3].get_text(" ", strip=True))
            entry = CaseEntry(
                tribunal=tribunal,
                case_family=case_family,
                case_number=case_number,
                case_status=case_status or "UNKNOWN",
                case_page_url=urljoin(page_url, case_link["href"]),
                page_url=page_url,
                accused_names=accused_names,
            )
            key = (_norm(entry.case_family), _norm(entry.case_number))
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
        return entries

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not _case_link(tribunal, href):
            continue
        text = _clean(anchor.get_text(" ", strip=True))
        parent = anchor.find_parent(["tr", "li", "article", "div", "section"])
        parent_text = _clean(parent.get_text(" ", strip=True)) if parent else text
        case_number = _extract_case_number(parent_text) or _extract_case_number(text)
        if not case_number:
            continue
        case_family = _extract_case_family(text or parent_text, case_number)
        if not case_family or len(case_family) < 3:
            continue
        case_status = _status_from_text(parent_text)
        accused_names = ""
        if tribunal == "IRMCT" and parent_text:
            accused_names = parent_text
        entry = CaseEntry(
            tribunal=tribunal,
            case_family=case_family,
            case_number=case_number,
            case_status=case_status or "UNKNOWN",
            case_page_url=urljoin(page_url, href),
            page_url=page_url,
            accused_names=accused_names,
        )
        key = (_norm(entry.case_family), _norm(entry.case_number))
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return entries


def _case_candidates_from_ucr(case_number: str, session: requests.Session | None) -> tuple[int, int, dict[str, int], str]:
    getter = session.get if session is not None else requests.get
    try:
        detail_resp = getter(
            "https://ucr.irmct.org/api/Summary/ByCaseDetail",
            params={"CaseNumber": case_number},
            timeout=60,
            headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"},
            verify=True,
        )
        detail_resp.raise_for_status()
        detail_payload = detail_resp.json()
        raw_detail = detail_payload.get("data", "[]")
        detail_rows = json.loads(raw_detail) if isinstance(raw_detail, str) else raw_detail
        if not detail_rows:
            return 0, 0, {}, "no_case_detail"
        resolved_case_number = str(detail_rows[0].get("CaseNumber") or case_number).strip()
        docs_resp = getter(
            "https://ucr.irmct.org/api/Summary/ByCaseDocsByLang",
            params={"CaseNumber": resolved_case_number, "Lang": "EN"},
            timeout=60,
            headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"},
            verify=True,
        )
        docs_resp.raise_for_status()
        docs_payload = docs_resp.json()
        raw_docs = docs_payload.get("data", "[]")
        docs = json.loads(raw_docs) if isinstance(raw_docs, str) else raw_docs
        if not isinstance(docs, list):
            docs = []
        counts: dict[str, int] = {}
        for doc in docs:
            doctype = _clean(doc.get("DocumentType") or "").upper() or "UNKNOWN"
            counts[doctype] = counts.get(doctype, 0) + 1
        tap_docs = counts.get("TAP", 0)
        transcript_docs = counts.get("TRS", 0) + counts.get("TRA", 0) + counts.get("TRN", 0)
        return tap_docs, transcript_docs, counts, "resolved"
    except Exception as exc:
        return 0, 0, {}, f"error: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover new tribunal source-manifest candidates from official tribunal case lists.")
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST), help="Current tribunal source manifest to exclude already-covered cases")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT), help="Review CSV for broadened tribunal candidates")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY), help="Summary JSON")
    parser.add_argument(
        "--official-case-list",
        action="append",
        default=[],
        help="Optional TRIBUNAL=URL override. May be repeated. Defaults to the official ICTR, ICTY, and IRMCT case pages.",
    )
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR login password")
    args = parser.parse_args()

    source_rows = read_csv_rows(Path(args.source_manifest)) if Path(args.source_manifest).exists() else []
    source_case_families = {_norm(row.get("case_family")) for row in source_rows if _norm(row.get("case_family"))}
    source_case_numbers = {_norm(row.get("case_number")) for row in source_rows if _norm(row.get("case_number"))}

    official_case_lists = dict(OFFICIAL_CASE_LISTS)
    for item in args.official_case_list:
        if "=" not in item:
            continue
        tribunal, url = item.split("=", 1)
        tribunal = tribunal.strip().upper()
        url = url.strip()
        if tribunal and url:
            official_case_lists[tribunal] = url

    session = None
    ucr_username = os.getenv(args.username_env, "").strip()
    ucr_password = os.getenv(args.password_env, "").strip()
    if ucr_username and ucr_password:
        from phase2.common import create_ucr_session

        session = create_ucr_session(ucr_username, ucr_password)
        print("UCR login: OK")

    review_rows: list[dict[str, object]] = []
    summary = {
        "source_manifest": str(Path(args.source_manifest)),
        "official_case_lists": official_case_lists,
        "official_cases_scanned": 0,
        "new_candidates": 0,
        "already_covered": 0,
        "broaden_now": 0,
        "hold_for_link_validation": 0,
        "manual_review": 0,
    }

    for tribunal, page_url in official_case_lists.items():
        try:
            case_entries = _parse_case_list_page(tribunal, page_url)
        except Exception as exc:
            review_rows.append(
                {
                    "tribunal": tribunal,
                    "case_family": "",
                    "case_number": "",
                    "candidate_priority": "LOW",
                    "has_video": "UNKNOWN",
                    "tap_count": "UNKNOWN",
                    "estimated_hours": "UNKNOWN",
                    "estimated_witnesses": "UNKNOWN",
                    "source_url": page_url,
                    "inventory_search_url": "",
                    "official_case_page_url": page_url,
                    "official_case_list_url": page_url,
                    "case_status": "ERROR",
                    "curation_action": "Fix crawler and retry.",
                    "include_in_tri_modal_set": "NO",
                    "recommended_action": "manual_review",
                    "recommended_score": "0",
                    "manual_selection": "NO",
                    "notes": f"crawl_error={exc}",
                }
            )
            continue

        summary["official_cases_scanned"] += len(case_entries)
        for entry in case_entries:
            if _norm(entry.case_family) in source_case_families or _norm(entry.case_number) in source_case_numbers:
                summary["already_covered"] += 1
                continue

            override = MANUAL_CURATION_OVERRIDES.get(_norm(entry.case_family), {})
            tap_docs, transcript_docs, doc_types, case_detail_status = _case_candidates_from_ucr(entry.case_number, session)
            if override:
                category = "hold_for_link_validation"
                candidate_priority = override.get("candidate_priority", "MEDIUM")
                recommended_action = override.get("recommended_action", "hold_for_link_validation")
                recommended_score = override.get("recommended_score", 120)
                content_type = override.get("content_type", "Transcript-only")
                include_flag = override.get("include_in_tri_modal_set", "ONLY_IF_VIDEO_LINKS_RESOLVED")
                curation_action = override.get("curation_action", "Manual override required.")
                has_video = override.get("has_video", "UNKNOWN_VERIFY_IN_UCR")
                estimated_hours = override.get("estimated_hours", "UNKNOWN")
                estimated_witnesses = override.get("estimated_witnesses", "UNKNOWN")
            elif tap_docs > 0:
                category = "broaden_now"
                candidate_priority = "HIGH"
                recommended_action = "broaden_now"
                content_type = "Witness testimony"
                include_flag = "YES_AFTER_LINK_VALIDATION"
                curation_action = "Case has TAP-bearing public records in UCR; promote into the tribunal bootstrap manifest."
                recommended_score = 100
                has_video = "YES"
                estimated_hours = "10-20"
                estimated_witnesses = "10-30 possible"
            elif transcript_docs > 0:
                category = "hold_for_link_validation"
                candidate_priority = "MEDIUM"
                recommended_action = "hold_for_link_validation"
                content_type = "Transcript-only"
                include_flag = "NO"
                curation_action = "Keep as transcript-only unless public recordings are later verified."
                recommended_score = 50
                has_video = "NO"
                estimated_hours = "5-10"
                estimated_witnesses = "5-15 possible"
            else:
                category = "manual_review"
                candidate_priority = "LOW"
                recommended_action = "manual_review"
                content_type = "Transcript-only"
                include_flag = "NO"
                curation_action = "No TAP docs resolved yet; inspect manually."
                recommended_score = 10
                has_video = "NO"
                estimated_hours = "UNKNOWN"
                estimated_witnesses = "UNKNOWN"

            summary[category] += 1
            score = int(recommended_score if recommended_score is not None else (100 if tap_docs > 0 else 50 if transcript_docs > 0 else 10))
            source_url = entry.case_page_url
            inventory_search_url = f"https://ucr.irmct.org/scasedocs/case/{entry.case_number}"
            notes = (
                f"Official case-list source={entry.page_url}; case_status={entry.case_status}; "
                f"case_detail_status={case_detail_status}; doc_types={json.dumps(doc_types, sort_keys=True)}; accused_names={entry.accused_names}"
            )
            if override.get("notes"):
                notes = f"{notes}; {override['notes']}"
            review_rows.append(
                {
                    "tribunal": entry.tribunal,
                    "case_family": entry.case_family,
                    "case_number": entry.case_number,
                    "candidate_priority": candidate_priority,
                    "has_video": has_video,
                    "tap_count": str(tap_docs),
                    "estimated_hours": estimated_hours,
                    "estimated_witnesses": estimated_witnesses,
                    "source_url": source_url,
                    "inventory_search_url": inventory_search_url,
                    "official_case_page_url": entry.case_page_url,
                    "official_case_list_url": entry.page_url,
                    "case_status": entry.case_status,
                    "curation_action": curation_action,
                    "include_in_tri_modal_set": include_flag,
                    "recommended_action": recommended_action,
                    "recommended_score": str(score),
                    "content_type": content_type,
                    "manual_selection": "NO",
                    "notes": notes,
                    "tap_doc_count": str(tap_docs),
                    "transcript_doc_count": str(transcript_docs),
                }
            )
            summary["new_candidates"] += 1

    review_rows.sort(
        key=lambda row: (
            -int(float(str(row.get("recommended_score") or 0).strip() or 0)),
            _norm(row.get("tribunal")),
            _norm(row.get("case_family")),
            _norm(row.get("case_number")),
        )
    )

    output_path = Path(args.output_csv)
    ensure_dir(output_path.parent)
    write_csv(
        output_path,
        review_rows,
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
            "official_case_page_url",
            "official_case_list_url",
            "case_status",
            "curation_action",
            "include_in_tri_modal_set",
            "recommended_action",
            "recommended_score",
            "content_type",
            "manual_selection",
            "notes",
            "tap_doc_count",
            "transcript_doc_count",
        ],
    )

    summary["output_csv"] = str(output_path)
    summary["review_rows"] = len(review_rows)
    summary_path = Path(args.summary_json)
    ensure_dir(summary_path.parent)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
