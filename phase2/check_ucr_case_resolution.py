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
    from phase2.common import create_ucr_session, read_csv_rows
else:
    from .common import create_ucr_session, read_csv_rows


UCR_BASE = "https://ucr.irmct.org"
CASE_HINTS = {
    "karadzic": ["IT-95-5/18"],
    "mladic": ["IT-09-92"],
    "popovic": ["IT-05-88"],
    "bagosora": ["ICTR-98-41-T"],
    "akayesu": ["ICTR-96-4-T"],
}


def _session_from_env(username_env: str, password_env: str) -> requests.Session | None:
    username = os.getenv(username_env, "").strip()
    password = os.getenv(password_env, "").strip()
    if not username or not password:
        return None
    return create_ucr_session(username, password)


def _get_json(session: requests.Session | None, path: str, params: dict[str, str]) -> dict[str, object]:
    getter = session.get if session is not None else requests.get
    resp = getter(f"{UCR_BASE}{path}", params=params, timeout=60, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True)
    resp.raise_for_status()
    return resp.json()


def _decode_api_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    raw = payload.get("data", "[]")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, list):
        return raw
    return []


def _case_candidates(case_name: str, case_id: str) -> list[str]:
    candidates: list[str] = []
    if case_id.strip():
        candidates.append(case_id.strip())
    key = re.sub(r"[^a-z0-9]+", " ", case_name.lower()).strip()
    for hint, vals in CASE_HINTS.items():
        if hint in key:
            for value in vals:
                if value not in candidates:
                    candidates.append(value)
    return candidates


def _summarize_docs(docs: list[dict[str, object]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for doc in docs:
        doctype = str(doc.get("DocumentType") or "").strip().upper() or "UNKNOWN"
        summary[doctype] = summary.get(doctype, 0) + 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Check UCR case resolution and recording availability for Phase 2 CSV rows")
    parser.add_argument("--source-csv", required=True, help="CSV to inspect")
    parser.add_argument("--case-name-column", default="case_name", help="Column containing the case name")
    parser.add_argument("--case-id-column", default="case_id", help="Column containing the case number if present")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit")
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR login password")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    session = _session_from_env(args.username_env, args.password_env)
    if session is not None:
        print("UCR login: OK")

    for idx, row in enumerate(rows, start=1):
        case_name = (row.get(args.case_name_column) or row.get("case_name") or row.get("case_family") or "").strip()
        case_id = (row.get(args.case_id_column) or row.get("case_id") or "").strip()
        candidates = _case_candidates(case_name, case_id)
        print("=" * 80)
        print(f"Row {idx}")
        print(f"case_name: {case_name}")
        print(f"case_id: {case_id or '(none)'}")
        print(f"candidates: {candidates or '(none)'}")

        if not candidates:
            print("resolution: no candidate case number available")
            continue

        for cand in candidates:
            try:
                detail = _decode_api_payload(_get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": cand}))
                if not detail:
                    print(f"case_number {cand}: no case detail returned")
                    continue
                case_desc = str(detail[0].get("CaseDescription") or "")
                docs_payload = _get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": cand, "Lang": "EN"})
                docs = _decode_api_payload(docs_payload)
                counts = _summarize_docs(docs)
                tap_docs = [d for d in docs if str(d.get("DocumentType") or "").strip().upper() == "TAP"]
                print(f"case_number {cand}: OK -> {case_desc}")
                print(f"  total_docs: {len(docs)}")
                print(f"  doc_types: {counts}")
                print(f"  tap_docs: {len(tap_docs)}")
                for doc in tap_docs[:5]:
                    title = str(doc.get("DocumentTitle") or "")
                    date = str(doc.get("DocSignatureDate") or "")
                    path = str(doc.get("DocumentPath") or "")
                    print(f"    - {date} | {title} | {path}")
            except Exception as exc:
                print(f"case_number {cand}: ERROR -> {exc}")


if __name__ == "__main__":
    main()
