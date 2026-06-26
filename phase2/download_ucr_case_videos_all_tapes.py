from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import create_ucr_session, ensure_dir, read_csv_rows, safe_filename, sha1_short, slugify, write_csv
else:
    from .common import create_ucr_session, ensure_dir, read_csv_rows, safe_filename, sha1_short, slugify, write_csv


UCR_BASE = "https://ucr.irmct.org"
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}
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


def _normalize_path(path: str) -> str:
    return path.replace("http://icr.icty.org/", "https://ucr.irmct.org/").replace("#", "%23")


def _download(url: str, dest: Path, session: requests.Session | None) -> Path:
    ensure_dir(dest.parent)
    getter = session.get if session is not None else requests.get
    with getter(url, timeout=120, stream=True, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True) as resp:
        resp.raise_for_status()
        with dest.open("wb") as out:
            for chunk in resp.iter_content(chunk_size=1024 * 128):
                if chunk:
                    out.write(chunk)
    return dest


def _case_number(case_name: str, case_id: str) -> str:
    if case_id.strip():
        return case_id.strip()
    lower = case_name.lower()
    for key, value in CASE_HINTS.items():
        if key in lower:
            return value
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Download all TAP videos for case-level planning manifest rows")
    parser.add_argument("--source-csv", required=True)
    parser.add_argument("--output-root", default="data/phase2/ucr_case_video_all_tapes")
    parser.add_argument("--index-csv", default="")
    parser.add_argument("--case-name-column", default="case_name")
    parser.add_argument("--case-id-column", default="case_id")
    parser.add_argument("--record-id-column", default="record_id")
    parser.add_argument("--username-env", default="UCR_USERNAME")
    parser.add_argument("--password-env", default="UCR_PASSWORD")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    session = _session_from_env(args.username_env, args.password_env)
    if session is not None:
        print("UCR login: OK")

    out = Path(args.output_root)
    raw_dir = ensure_dir(out / "raw")
    index_dir = ensure_dir(out / "index")
    index_csv = Path(args.index_csv) if args.index_csv else index_dir / "ucr_case_videos_all_tapes.csv"

    out_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows, start=1):
        record_id = (row.get(args.record_id_column) or row.get("subset_id") or f"record_{idx}").strip()
        case_name = (row.get(args.case_name_column) or row.get("case_name") or row.get("case_family") or "").strip()
        case_id = (row.get(args.case_id_column) or row.get("case_id") or "").strip()
        case_number = _case_number(case_name, case_id)
        if not case_number:
            out_rows.append(
                {
                    "sample_id": record_id,
                    "record_id": record_id,
                    "case_name": case_name,
                    "case_id": case_id,
                    "resolved_case_number": "",
                    "document_title": "",
                    "document_type": "",
                    "doc_signature_date": "",
                    "resolved_video_url": "",
                    "local_video_path": "",
                    "download_status": "skipped",
                    "skip_reason": "no case number candidate available",
                }
            )
            continue

        detail = _decode_api_payload(_get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": case_number}))
        if not detail:
            out_rows.append(
                {
                    "sample_id": record_id,
                    "record_id": record_id,
                    "case_name": case_name,
                    "case_id": case_id,
                    "resolved_case_number": case_number,
                    "document_title": "",
                    "document_type": "",
                    "doc_signature_date": "",
                    "resolved_video_url": "",
                    "local_video_path": "",
                    "download_status": "skipped",
                    "skip_reason": f"no case detail returned for {case_number}",
                }
            )
            continue

        docs = _decode_api_payload(_get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": case_number, "Lang": "EN"}))
        tap_docs = [d for d in docs if str(d.get("DocumentType") or "").strip().upper() == "TAP"]
        if not tap_docs:
            tap_docs = _decode_api_payload(_get_json(session, "/api/Summary/ByMainCase", {"CaseNumber": case_number, "Lang": "EN"}))
            tap_docs = [d for d in tap_docs if str(d.get("DocumentType") or "").strip().upper() == "TAP"]

        if not tap_docs:
            out_rows.append(
                {
                    "sample_id": record_id,
                    "record_id": record_id,
                    "case_name": case_name,
                    "case_id": case_id,
                    "resolved_case_number": case_number,
                    "document_title": "",
                    "document_type": "",
                    "doc_signature_date": "",
                    "resolved_video_url": "",
                    "local_video_path": "",
                    "download_status": "skipped",
                    "skip_reason": f"no TAP recordings for {case_number}",
                }
            )
            continue

        for doc_idx, doc in enumerate(tap_docs, start=1):
            raw_url = _normalize_path(str(doc.get("DocumentPath") or "").strip())
            if not raw_url:
                continue
            suffix = Path(urlparse(raw_url).path).suffix.lower() or ".mp4"
            if suffix not in VIDEO_SUFFIXES:
                suffix = ".mp4"
            case_slug = slugify(case_name or case_number or record_id)
            doc_stem = safe_filename(raw_url, f"{case_slug}_{doc_idx}_{sha1_short(raw_url)}{suffix}")
            if not Path(doc_stem).suffix:
                doc_stem = f"{doc_stem}{suffix}"
            dest = raw_dir / case_slug / doc_stem
            if dest.exists():
                download_status = "exists"
            else:
                _download(raw_url, dest, session)
                download_status = "downloaded"
            out_rows.append(
                {
                    "sample_id": f"{record_id}_{doc_idx}",
                    "record_id": record_id,
                    "case_name": case_name,
                    "case_id": case_id,
                    "resolved_case_number": case_number,
                    "document_title": str(doc.get("DocumentTitle") or ""),
                    "document_type": str(doc.get("DocumentType") or ""),
                    "doc_signature_date": str(doc.get("DocSignatureDate") or ""),
                    "resolved_video_url": raw_url,
                    "local_video_path": str(dest),
                    "download_status": download_status,
                    "skip_reason": "",
                }
            )
            print(f"row={idx} case_name={case_name!r} recording={doc_idx} status={download_status}")

    write_csv(
        index_csv,
        out_rows,
        [
            "sample_id",
            "record_id",
            "case_name",
            "case_id",
            "resolved_case_number",
            "document_title",
            "document_type",
            "doc_signature_date",
            "resolved_video_url",
            "local_video_path",
            "download_status",
            "skip_reason",
        ],
    )
    print(f"Wrote {len(out_rows)} TAP recording rows to {index_csv}")


if __name__ == "__main__":
    main()
