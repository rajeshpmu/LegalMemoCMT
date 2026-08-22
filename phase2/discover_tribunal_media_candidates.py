from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import create_ucr_session, read_csv_rows, write_csv
else:
    from .common import create_ucr_session, read_csv_rows, write_csv


UCR_BASE = "https://ucr.irmct.org"
DEFAULT_SOURCE = Path("data/processed/phase2/expanded_planning_missing_sources.csv")
DEFAULT_LEDGER = Path("data/phase2/source_manifests/case_candidate_ledger.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/tribunal_media_discovery.csv")
DEFAULT_SUMMARY = Path("reports/phase2/tribunal_media_discovery_summary.json")

PLACEHOLDER_CASE_NUMBERS = {
    "",
    "tbd",
    "to_be_filled",
    "unknown",
    "ict r case family",
    "ictr case family",
    "mict cases",
    "mict case",
}


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return text or "item"


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


def _split_case_numbers(raw: str) -> list[str]:
    raw = str(raw or "").strip()
    if not raw:
        return []
    parts = re.split(r"\s+/\s+|[,;|]+", raw)
    cleaned: list[str] = []
    for part in parts:
        value = part.strip()
        if not value:
            continue
        if _norm(value) in PLACEHOLDER_CASE_NUMBERS:
            continue
        if value not in cleaned:
            cleaned.append(value)
        if value.upper().endswith("-T"):
            stripped = value[:-2].rstrip("-")
            if stripped and stripped not in cleaned and _norm(stripped) not in PLACEHOLDER_CASE_NUMBERS:
                cleaned.append(stripped)
    return cleaned


def _key_tokens(text: str) -> set[str]:
    tokens = {token for token in re.split(r"[^a-z0-9]+", _norm(text)) if token}
    tokens -= {"trial", "case", "cases", "related", "hearing", "hearings", "et", "al"}
    return tokens


def _transcript_like(doc: dict[str, object]) -> bool:
    doc_type = _norm(doc.get("DocumentType")).upper()
    title = _norm(doc.get("DocumentTitle"))
    path = _norm(doc.get("DocumentPath"))
    return (
        doc_type in {"TRS", "TRN", "TRANSCRIPT"}
        or "transcript" in title
        or "transcript" in path
        or "trs" in title
    )


def _candidate_case_numbers(
    row: dict[str, str],
    ledger_map: dict[str, list[str]],
) -> list[str]:
    candidates: list[str] = []
    for field in ("case_number", "case_id", "source_case_number"):
        for value in _split_case_numbers(row.get(field, "")):
            if value not in candidates:
                candidates.append(value)
    key = _norm(row.get("case_name") or row.get("case_family") or row.get("case_description"))
    if key in ledger_map:
        for value in ledger_map[key]:
            if value not in candidates:
                candidates.append(value)
    source_tokens = _key_tokens(key)
    if source_tokens:
        scored: list[tuple[int, str]] = []
        for ledger_key, case_numbers in ledger_map.items():
            ledger_tokens = _key_tokens(ledger_key)
            overlap = len(source_tokens & ledger_tokens)
            if overlap == 0:
                continue
            if key in ledger_key or ledger_key in key:
                overlap += 2
            scored.append((overlap, ledger_key))
        scored.sort(key=lambda item: (-item[0], item[1]))
        for _, ledger_key in scored:
            for value in ledger_map.get(ledger_key, []):
                if value not in candidates:
                    candidates.append(value)
    return candidates


def _build_ledger_map(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    ledger_map: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        family = _norm(row.get("case_family") or row.get("case_name"))
        if not family:
            continue
        for value in _split_case_numbers(row.get("case_number") or ""):
            if value not in ledger_map[family]:
                ledger_map[family].append(value)
    return dict(ledger_map)


def _doc_counts(docs: list[dict[str, object]]) -> dict[str, object]:
    summary: Counter[str] = Counter()
    transcript_docs: list[dict[str, object]] = []
    tap_docs: list[dict[str, object]] = []
    for doc in docs:
        doctype = _norm(doc.get("DocumentType")).upper() or "UNKNOWN"
        summary[doctype] += 1
        if doctype == "TAP":
            tap_docs.append(doc)
        if _transcript_like(doc):
            transcript_docs.append(doc)
    return {
        "doc_types": dict(sorted(summary.items())),
        "tap_docs": tap_docs,
        "transcript_docs": transcript_docs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover tribunal cases/hearings with valid videos from missing planning rows.")
    parser.add_argument("--source-csv", default=str(DEFAULT_SOURCE), help="Missing planning rows CSV")
    parser.add_argument("--ledger-csv", default=str(DEFAULT_LEDGER), help="Candidate ledger for case-number hints")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT), help="Media discovery CSV")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY), help="Summary JSON")
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR login password")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit")
    args = parser.parse_args()

    source_rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        source_rows = source_rows[: args.limit]

    ledger_rows = read_csv_rows(Path(args.ledger_csv)) if Path(args.ledger_csv).exists() else []
    ledger_map = _build_ledger_map(ledger_rows)

    session = _session_from_env(args.username_env, args.password_env)
    if session is not None:
        print("UCR login: OK")

    out_rows: list[dict[str, object]] = []
    stats = Counter()
    for idx, row in enumerate(source_rows, start=1):
        case_name = (row.get("case_name") or row.get("case_family") or "").strip()
        tribunal = (row.get("tribunal") or "").strip()
        source_id = (row.get("source_id") or f"source_{idx}").strip()
        candidate_case_numbers = _candidate_case_numbers(row, ledger_map)

        stats["rows_inspected"] += 1
        if not candidate_case_numbers:
            stats["unresolved_rows"] += 1
            out_rows.append(
                {
                    "row_number": idx,
                    "source_id": source_id,
                    "tribunal": tribunal,
                    "case_name": case_name,
                    "candidate_case_numbers": "",
                    "resolved_case_number": "",
                    "case_detail_status": "no_case_number_candidate",
                    "doc_types": "{}",
                    "total_docs": 0,
                    "tap_doc_count": 0,
                    "transcript_doc_count": 0,
                    "media_status": "unresolved",
                    "recommended_action": "manual_search",
                    "notes": "No usable case-number candidate could be derived from the missing-source row or candidate ledger.",
                }
            )
            continue

        resolved_case_number = ""
        case_detail_status = "no_case_detail"
        docs: list[dict[str, object]] = []
        docs_source = ""
        for case_number in candidate_case_numbers:
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
                docs_payload = _get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": resolved_case_number, "Lang": "EN"})
                docs = _decode_payload(docs_payload)
                docs_source = "ByCaseDocsByLang"
                if not docs:
                    docs = _decode_payload(_get_json(session, "/api/Summary/ByMainCase", {"CaseNumber": resolved_case_number, "Lang": "EN"}))
                    docs_source = "ByMainCase"
            except Exception as exc:
                docs = []
                docs_source = f"error: {exc}"
            break

        counts = _doc_counts(docs)
        tap_docs = counts["tap_docs"]
        transcript_docs = counts["transcript_docs"]
        doc_types = counts["doc_types"]
        tap_count = len(tap_docs)
        transcript_count = len(transcript_docs)
        total_docs = len(docs)

        if case_detail_status != "resolved":
            stats["unresolved_rows"] += 1
            media_status = "unresolved"
            recommended_action = "manual_search"
        elif tap_count > 0:
            stats["video_bearing_rows"] += 1
            media_status = "video_bearing"
            recommended_action = "video_candidate"
        elif transcript_count > 0 or total_docs > 0:
            stats["transcript_only_rows"] += 1
            media_status = "transcript_only"
            recommended_action = "keep_transcript_only"
        else:
            stats["no_documents_rows"] += 1
            media_status = "no_documents"
            recommended_action = "manual_search"

        tap_titles = [str(doc.get("DocumentTitle") or "").strip() for doc in tap_docs[:10] if str(doc.get("DocumentTitle") or "").strip()]
        tap_dates = [str(doc.get("DocSignatureDate") or "").strip() for doc in tap_docs[:10] if str(doc.get("DocSignatureDate") or "").strip()]
        transcript_titles = [str(doc.get("DocumentTitle") or "").strip() for doc in transcript_docs[:10] if str(doc.get("DocumentTitle") or "").strip()]

        out_rows.append(
            {
                "row_number": idx,
                "source_id": source_id,
                "tribunal": tribunal,
                "case_name": case_name,
                "candidate_case_numbers": " | ".join(candidate_case_numbers),
                "resolved_case_number": resolved_case_number,
                "case_detail_status": case_detail_status,
                "docs_source": docs_source,
                "total_docs": total_docs,
                "tap_doc_count": tap_count,
                "transcript_doc_count": transcript_count,
                "doc_types": json.dumps(doc_types, sort_keys=True),
                "tap_doc_titles": " | ".join(tap_titles),
                "tap_doc_dates": " | ".join(tap_dates),
                "transcript_doc_titles": " | ".join(transcript_titles),
                "media_status": media_status,
                "recommended_action": recommended_action,
                "notes": row.get("notes", ""),
            }
        )

    output_path = Path(args.output_csv)
    write_csv(
        output_path,
        out_rows,
        [
            "row_number",
            "source_id",
            "tribunal",
            "case_name",
            "candidate_case_numbers",
            "resolved_case_number",
            "case_detail_status",
            "docs_source",
            "total_docs",
            "tap_doc_count",
            "transcript_doc_count",
            "doc_types",
            "tap_doc_titles",
            "tap_doc_dates",
            "transcript_doc_titles",
            "media_status",
            "recommended_action",
            "notes",
        ],
    )

    summary = {
        "source_csv": str(Path(args.source_csv)),
        "ledger_csv": str(Path(args.ledger_csv)),
        "output_csv": str(output_path),
        "rows_inspected": int(stats["rows_inspected"]),
        "video_bearing_rows": int(stats["video_bearing_rows"]),
        "transcript_only_rows": int(stats["transcript_only_rows"]),
        "no_documents_rows": int(stats["no_documents_rows"]),
        "unresolved_rows": int(stats["unresolved_rows"]),
        "video_bearing_case_names": sorted(
            {
                row["case_name"]
                for row in out_rows
                if row.get("media_status") == "video_bearing" and str(row.get("case_name") or "").strip()
            }
        ),
        "transcript_only_case_names": sorted(
            {
                row["case_name"]
                for row in out_rows
                if row.get("media_status") == "transcript_only" and str(row.get("case_name") or "").strip()
            }
        ),
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
