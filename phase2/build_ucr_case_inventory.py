from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import create_ucr_session, read_csv_rows, write_csv
else:
    from .common import create_ucr_session, read_csv_rows, write_csv


UCR_BASE = "https://ucr.irmct.org"
CASE_HINTS = {
    "karadzic": "IT-95-5/18",
    "mladic": "IT-09-92",
    "popovic": "IT-05-88",
    "bagosora": "ICTR-98-41-T",
    "akayesu": "ICTR-96-4-T",
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


def _normalize_url(url: str) -> str:
    url = url.replace("http://icr.icty.org/", "https://ucr.irmct.org/")
    return url.replace("#", "%23")


def _resolve_case_number(case_name: str, case_id: str) -> str:
    if case_id.strip():
        return case_id.strip()
    key = re.sub(r"[^a-z0-9]+", " ", case_name.lower()).strip()
    for hint, case_number in CASE_HINTS.items():
        if hint in key:
            return case_number
    return ""


def _looks_like_video(url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix in {".mp4", ".webm", ".mov", ".mkv", ".m4v"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Enumerate UCR recordings for planning-manifest rows")
    parser.add_argument("--source-csv", required=True, help="Planning manifest CSV")
    parser.add_argument("--output-csv", default="data/processed/phase2/ucr_case_inventory.csv", help="Output inventory CSV")
    parser.add_argument("--case-name-column", default="case_name", help="Column containing case name")
    parser.add_argument("--case-id-column", default="case_id", help="Column containing a case number if present")
    parser.add_argument("--record-id-column", default="record_id", help="Column used to form a stable id")
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing UCR login password")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    session = _session_from_env(args.username_env, args.password_env)
    if session is not None:
        print("UCR login: OK")

    out_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=1):
        record_id = (row.get(args.record_id_column) or row.get("subset_id") or row.get("manifest_id") or f"record_{idx}").strip()
        case_name = (row.get(args.case_name_column) or row.get("case_name") or row.get("case_family") or "").strip()
        case_id = (row.get(args.case_id_column) or row.get("case_id") or "").strip()
        case_number = _resolve_case_number(case_name, case_id)
        status = "skipped"
        case_desc = ""
        docs: list[dict[str, object]] = []
        skip_reason = ""
        if case_number:
            detail = _decode_api_payload(_get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": case_number}))
            if detail:
                case_desc = str(detail[0].get("CaseDescription") or "")
                docs_payload = _get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": case_number, "Lang": "EN"})
                docs = _decode_api_payload(docs_payload)
                if not docs:
                    docs = _decode_api_payload(_get_json(session, "/api/Summary/ByMainCase", {"CaseNumber": case_number, "Lang": "EN"}))
                status = "ok" if docs else "no_docs"
                if not docs:
                    skip_reason = "no documents returned by UCR"
            else:
                skip_reason = f"no case detail returned for {case_number}"
        else:
            skip_reason = "no case number candidate available"

        for doc_idx, doc in enumerate(docs, start=1):
            doc_path = _normalize_url(str(doc.get("DocumentPath") or "").strip())
            out_rows.append(
                {
                    "inventory_id": f"{record_id}_{doc_idx}",
                    "source_record_id": record_id,
                    "case_name": case_name,
                    "case_number": case_number,
                    "case_description": case_desc,
                    "document_title": str(doc.get("DocumentTitle") or ""),
                    "document_type": str(doc.get("DocumentType") or ""),
                    "doc_signature_date": str(doc.get("DocSignatureDate") or ""),
                    "doc_source_desc": str(doc.get("DocSourceDesc") or ""),
                    "document_path": doc_path,
                    "is_video": str(doc_path and _looks_like_video(doc_path)).lower(),
                    "source_status": status,
                    "skip_reason": skip_reason,
                }
            )

        print(
            f"row={idx} case_name={case_name!r} case_number={case_number or '(none)'} "
            f"docs={len(docs)} status={status} reason={skip_reason or '(none)'}"
        )

    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "inventory_id",
            "source_record_id",
            "case_name",
            "case_number",
            "case_description",
            "document_title",
            "document_type",
            "doc_signature_date",
            "doc_source_desc",
            "document_path",
            "is_video",
            "source_status",
            "skip_reason",
        ],
    )
    print(f"Wrote {len(out_rows)} inventory rows to {args.output_csv}")


if __name__ == "__main__":
    main()
