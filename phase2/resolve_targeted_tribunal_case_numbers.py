from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import create_ucr_session, read_csv_rows, write_csv
else:
    from .common import create_ucr_session, read_csv_rows, write_csv


UCR_BASE = "https://ucr.irmct.org"
DEFAULT_SOURCE = Path("data/processed/phase2/tribunal_media_discovery.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/tribunal_case_resolution_review.csv")
DEFAULT_SUMMARY = Path("reports/phase2/tribunal_case_resolution_review_summary.json")

# These are the families that still need stronger case-number resolution.
# The candidates come from public tribunal case pages and UCR case IDs.
TARGET_FAMILY_HINTS = {
    "akayesu": ["ICTR-96-04", "ICTR-96-4-T", "ICTR-96-04-T"],
    "ntakirutimana": ["ICTR-96-17", "ICTR-96-17-T"],
    "ntahobali": ["ICTR-98-42", "ICTR-98-42-T", "ICTR-97-21", "ICTR-97-21-T"],
    "irmct hearings": [],
}


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _session_from_env(username_env: str, password_env: str) -> requests.Session | None:
    username = os.getenv(username_env, "").strip()
    password = os.getenv(password_env, "").strip()
    if not username or not password:
        return None
    return create_ucr_session(username, password)


def _get_json(session: requests.Session | None, path: str, params: dict[str, str]) -> dict[str, object]:
    getter = session.get if session is not None else requests.get
    resp = getter(
        f"{UCR_BASE}{path}",
        params=params,
        timeout=60,
        headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"},
        verify=True,
    )
    resp.raise_for_status()
    return resp.json()


def _decode_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    raw = payload.get("data", "[]")
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except Exception:
            return []
        return decoded if isinstance(decoded, list) else []
    if isinstance(raw, list):
        return raw
    return []


def _doc_counts(docs: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for doc in docs:
        doctype = str(doc.get("DocumentType") or "").strip().upper() or "UNKNOWN"
        counts[doctype] = counts.get(doctype, 0) + 1
    return dict(sorted(counts.items()))


def _candidate_numbers(case_name: str) -> list[str]:
    key = _norm(case_name)
    candidates: list[str] = []
    for hint, values in TARGET_FAMILY_HINTS.items():
        if hint in key:
            for value in values:
                if value not in candidates:
                    candidates.append(value)
    return candidates


def _family_tokens(text: str) -> set[str]:
    tokens = {token for token in re.split(r"[^a-z0-9]+", _norm(text)) if token}
    return tokens - {"cases", "case", "related", "family", "hearings"}


def _matches_target(case_name: str, targets: set[str]) -> bool:
    key = _norm(case_name)
    if key in targets:
        return True
    case_tokens = _family_tokens(case_name)
    for target in targets:
        target_tokens = _family_tokens(target)
        if case_tokens and target_tokens and case_tokens & target_tokens:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Attempt better case-number resolution for unresolved tribunal families.")
    parser.add_argument("--source-csv", default=str(DEFAULT_SOURCE), help="Media discovery CSV")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT), help="Resolution review CSV")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY), help="Summary JSON")
    parser.add_argument("--target-families", default="Akayesu,Ntakirutimana / Ntahobali related cases,IRMCT Hearings", help="Comma-separated family names to inspect")
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR login password")
    args = parser.parse_args()

    source_rows = read_csv_rows(Path(args.source_csv))
    targets = {_norm(item) for item in args.target_families.split(",") if _norm(item)}

    session = _session_from_env(args.username_env, args.password_env)
    if session is not None:
        print("UCR login: OK")

    out_rows: list[dict[str, object]] = []
    summary = {
        "source_csv": str(Path(args.source_csv)),
        "output_csv": str(Path(args.output_csv)),
        "target_families": sorted(targets),
        "rows_inspected": 0,
        "resolved_rows": 0,
        "unresolved_rows": 0,
        "resolved_case_numbers": [],
    }

    for idx, row in enumerate(source_rows, start=1):
        case_name = (row.get("case_name") or row.get("case_family") or "").strip()
        if not _matches_target(case_name, targets):
            continue
        summary["rows_inspected"] += 1
        candidates = _candidate_numbers(case_name)
        resolved_case_number = ""
        case_detail_status = "no_case_detail"
        docs_source = ""
        doc_types: dict[str, int] = {}
        total_docs = 0
        tap_count = 0
        transcript_count = 0
        for case_number in candidates:
            try:
                detail = _decode_payload(_get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": case_number}))
            except Exception as exc:
                case_detail_status = f"error: {exc}"
                continue
            if not detail:
                continue
            resolved_case_number = str(detail[0].get("CaseNumber") or case_number).strip()
            case_detail_status = "resolved"
            try:
                docs = _decode_payload(_get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": resolved_case_number, "Lang": "EN"}))
                docs_source = "ByCaseDocsByLang"
                if not docs:
                    docs = _decode_payload(_get_json(session, "/api/Summary/ByMainCase", {"CaseNumber": resolved_case_number, "Lang": "EN"}))
                    docs_source = "ByMainCase"
            except Exception as exc:
                docs = []
                docs_source = f"error: {exc}"
            doc_types = _doc_counts(docs)
            total_docs = len(docs)
            tap_count = doc_types.get("TAP", 0)
            transcript_count = doc_types.get("TRA", 0) + doc_types.get("TRS", 0) + doc_types.get("TRN", 0)
            break

        if resolved_case_number:
            summary["resolved_rows"] += 1
            summary["resolved_case_numbers"].append(resolved_case_number)
            resolution_status = "resolved"
        else:
            summary["unresolved_rows"] += 1
            resolution_status = "unresolved"

        out_rows.append(
            {
                "row_number": idx,
                "source_case_name": case_name,
                "candidate_case_numbers": " | ".join(candidates),
                "resolved_case_number": resolved_case_number,
                "resolution_status": resolution_status,
                "case_detail_status": case_detail_status,
                "docs_source": docs_source,
                "total_docs": total_docs,
                "tap_doc_count": tap_count,
                "transcript_doc_count": transcript_count,
                "doc_types": json.dumps(doc_types, sort_keys=True),
                "notes": row.get("notes", ""),
            }
        )

    output_path = Path(args.output_csv)
    write_csv(
        output_path,
        out_rows,
        [
            "row_number",
            "source_case_name",
            "candidate_case_numbers",
            "resolved_case_number",
            "resolution_status",
            "case_detail_status",
            "docs_source",
            "total_docs",
            "tap_doc_count",
            "transcript_doc_count",
            "doc_types",
            "notes",
        ],
    )

    summary["resolved_case_numbers"] = sorted({num for num in summary["resolved_case_numbers"] if num})
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
