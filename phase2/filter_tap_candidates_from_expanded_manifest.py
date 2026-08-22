from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import requests

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import create_ucr_session, ensure_dir, read_csv_rows, write_csv
else:
    from .common import create_ucr_session, ensure_dir, read_csv_rows, write_csv


UCR_BASE = "https://ucr.irmct.org"

# The expanded planning manifest is still a planning layer, so this script
# uses a small case-name hint map to resolve the rows to the UCR APIs.
CASE_NAME_HINTS = {
    "karadzic": ["IT-95-5/18"],
    "mladic": ["IT-09-92"],
    "popovic": ["IT-05-88"],
    "perisic": ["IT-04-81"],
    "bagosora": ["ICTR-98-41", "ICTR-98-41-T"],
    "akayesu": ["ICTR-96-04", "ICTR-96-4-T"],
    "nahimana": ["ICTR-99-52", "ICTR-99-52-T"],
    "karemera": ["ICTR-98-44", "ICTR-98-44-T"],
}


def normalize(text: object) -> str:
    return str(text or "").strip()


def case_candidates(case_name: str) -> list[str]:
    key = re.sub(r"[^a-z0-9]+", " ", case_name.lower()).strip()
    candidates: list[str] = []
    for hint, values in CASE_NAME_HINTS.items():
        if hint in key:
            for value in values:
                if value not in candidates:
                    candidates.append(value)
    return candidates


def session_from_env(username_env: str, password_env: str) -> requests.Session | None:
    username = os.getenv(username_env, "").strip()
    password = os.getenv(password_env, "").strip()
    if not username or not password:
        return None
    return create_ucr_session(username, password)


def get_json(session: requests.Session | None, path: str, params: dict[str, str]) -> dict[str, object]:
    getter = session.get if session is not None else requests.get
    resp = getter(f"{UCR_BASE}{path}", params=params, timeout=60, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True)
    resp.raise_for_status()
    return resp.json()


def decode_payload(payload: dict[str, object]) -> list[dict[str, object]]:
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


def summarize_doc_types(rows: list[dict[str, object]]) -> dict[str, int]:
    summary: Counter[str] = Counter()
    for row in rows:
        doctype = normalize(row.get("DocumentType")).upper() or "UNKNOWN"
        summary[doctype] += 1
    return dict(sorted(summary.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter expanded tribunal planning rows to TAP-bearing candidates.")
    parser.add_argument(
        "--input-csv",
        default="data/processed/phase2/phase2_expanded_planning_manifest.csv",
        help="Expanded planning manifest CSV",
    )
    parser.add_argument(
        "--output-csv",
        default="data/processed/phase2/tap_candidate_manifest.csv",
        help="Filtered TAP candidate manifest CSV",
    )
    parser.add_argument(
        "--summary-json",
        default="reports/phase2/tap_candidate_manifest_summary.json",
        help="Summary JSON for the filtered manifest",
    )
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR login password")
    args = parser.parse_args()

    session = session_from_env(args.username_env, args.password_env)
    if session is not None:
        print("UCR login: OK")

    rows = read_csv_rows(Path(args.input_csv))
    kept_rows: list[dict[str, object]] = []
    inspected = 0

    for index, row in enumerate(rows, start=1):
        inspected += 1
        case_name = normalize(row.get("case_name") or row.get("case_family"))
        candidates = case_candidates(case_name)
        if not candidates:
            continue

        resolved_case_number = ""
        resolved_case_description = ""
        resolved_docs: list[dict[str, object]] = []
        for candidate in candidates:
            detail = decode_payload(get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": candidate}))
            if not detail:
                continue
            resolved_case_number = normalize(detail[0].get("CaseNumber") or candidate)
            resolved_case_description = normalize(detail[0].get("CaseDescription") or case_name)
            docs = decode_payload(get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": resolved_case_number, "Lang": "EN"}))
            tap_docs = [doc for doc in docs if normalize(doc.get("DocumentType")).upper() == "TAP"]
            if tap_docs:
                resolved_docs = tap_docs
                break

        if not resolved_docs:
            continue

        kept_rows.append(
            {
                **row,
                "row_number": index,
                "resolved_case_number": resolved_case_number,
                "resolved_case_description": resolved_case_description,
                "tap_docs": len(resolved_docs),
                "total_docs": len(resolved_docs),
                "doc_types": json.dumps(summarize_doc_types(resolved_docs), sort_keys=True),
                "tap_doc_titles": " | ".join(normalize(doc.get("DocumentTitle")) for doc in resolved_docs[:10] if normalize(doc.get("DocumentTitle"))),
                "tap_doc_dates": " | ".join(normalize(doc.get("DocSignatureDate")) for doc in resolved_docs[:10] if normalize(doc.get("DocSignatureDate"))),
                "tap_candidate_status": "kept",
            }
        )

    fieldnames = list(kept_rows[0].keys()) if kept_rows else []
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if kept_rows:
        write_csv(output_path, kept_rows, fieldnames)
    else:
        write_csv(output_path, [], fieldnames or ["tap_candidate_status"])

    summary = {
        "input_csv": str(Path(args.input_csv)),
        "output_csv": str(output_path),
        "summary_json": str(Path(args.summary_json)),
        "rows_inspected": inspected,
        "rows_kept": len(kept_rows),
        "case_names_kept": sorted({normalize(row.get("case_name") or row.get("case_family")) for row in kept_rows if normalize(row.get("case_name") or row.get("case_family"))}),
    }
    summary_path = Path(args.summary_json)
    ensure_dir(summary_path.parent)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
