from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
DIRECT_MEDIA_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}

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
    path = path.replace("http://icr.icty.org/", "https://ucr.irmct.org/")
    path = path.replace("#", "%23")
    return path


def _download(url: str, dest: Path, session: requests.Session | None) -> Path:
    ensure_dir(dest.parent)
    getter = session.get if session is not None else requests.get
    with getter(url, timeout=120, stream=True, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True) as resp:
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").lower()
        if "text/html" in content_type or "application/xhtml+xml" in content_type:
            raise ValueError(f"Refusing HTML response for media URL: {url}")
        first = True
        with dest.open("wb") as out:
            for chunk in resp.iter_content(chunk_size=1024 * 128):
                if not chunk:
                    continue
                if first:
                    first = False
                    head = chunk.lstrip().lower()
                    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
                        raise ValueError(f"Refusing HTML payload for media URL: {url}")
                out.write(chunk)
    return dest


def verify_media(path: Path) -> None:
    subprocess.run(["file", str(path)], check=True)
    subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", str(path)], check=True)


def _case_candidates(case_name: str, case_id: str) -> list[str]:
    candidates: list[str] = []
    if case_id.strip():
        candidates.append(case_id.strip())
    key = re.sub(r"[^a-z0-9]+", " ", case_name.lower()).strip()
    for hint, case_number in CASE_HINTS.items():
        if hint in key and case_number not in candidates:
            candidates.append(case_number)
    return candidates


def _looks_like_direct_media_url(url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    return bool(url) and suffix in DIRECT_MEDIA_SUFFIXES


def _pick_recordings(docs: list[dict[str, object]], *, allow_non_tap: bool, title_contains: str, date: str, index: int) -> tuple[list[dict[str, object]], str]:
    reason = "filtered to TAP"
    if allow_non_tap:
        reason = "fallback to any document type"
        candidates = docs
    else:
        candidates = [d for d in docs if str(d.get("DocumentType") or "").strip().upper() == "TAP"]

    if date.strip():
        candidates = [d for d in candidates if str(d.get("DocSignatureDate") or "").strip() == date.strip()]
    if title_contains.strip():
        needle = title_contains.strip().lower()
        candidates = [d for d in candidates if needle in str(d.get("DocumentTitle") or "").lower()]
    candidates = sorted(candidates, key=lambda d: str(d.get("DocumentTitle") or ""))
    return candidates, reason


def _resolve_case_number(case_name: str, case_id: str) -> str:
    if case_id.strip():
        return case_id.strip()
    key = re.sub(r"[^a-z0-9]+", " ", case_name.lower()).strip()
    for hint, case_number in CASE_HINTS.items():
        if hint in key:
            return case_number
    return ""


def _try_case(session: requests.Session | None, case_number: str, *, title_contains: str, date: str, index: int, allow_non_tap: bool) -> tuple[str, list[dict[str, object]], list[dict[str, object]], str]:
    detail_payload = _decode_api_payload(_get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": case_number}))
    if not detail_payload:
        return "", [], [], f"no case detail returned for {case_number}"
    docs_payload = _get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": case_number, "Lang": "EN"})
    docs = _decode_api_payload(docs_payload)
    records, mode = _pick_recordings(docs, allow_non_tap=allow_non_tap, title_contains=title_contains, date=date, index=index)
    if records:
        return str(detail_payload[0].get("CaseDescription") or case_number), docs, records, mode
    main_payload = _decode_api_payload(_get_json(session, "/api/Summary/ByMainCase", {"CaseNumber": case_number, "Lang": "EN"}))
    main_records, main_mode = _pick_recordings(main_payload, allow_non_tap=allow_non_tap, title_contains=title_contains, date=date, index=index)
    if main_records:
        return str(detail_payload[0].get("CaseDescription") or case_number), main_payload, main_records, f"ByMainCase fallback; {main_mode}"
    return str(detail_payload[0].get("CaseDescription") or case_number), docs, [], "no matching recordings in ByCaseDocsByLang or ByMainCase"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download UCR recordings with ByCaseDocsByLang/ByMainCase fallback")
    parser.add_argument("--source-csv", required=True, help="CSV to inspect")
    parser.add_argument("--output-root", default="data/phase2/ucr_case_video_fallbacks", help="Download root")
    parser.add_argument("--index-csv", default="", help="Optional output index CSV")
    parser.add_argument("--case-name-column", default="case_name", help="Column containing the case name")
    parser.add_argument("--case-id-column", default="case_id", help="Column containing an explicit case number if present")
    parser.add_argument("--record-id-column", default="record_id", help="Column used for stable row ids")
    parser.add_argument("--video-url-column", default="video_url", help="Column that may contain a direct media URL")
    parser.add_argument("--title-contains", default="", help="Optional substring filter for recording titles")
    parser.add_argument("--date", default="", help="Optional exact tape date filter in DD/MM/YYYY")
    parser.add_argument("--index", type=int, default=1, help="1-based index among filtered recordings")
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR login password")
    parser.add_argument("--require-login", action="store_true", help="Fail if a UCR login cannot be established")
    parser.add_argument("--verify", action="store_true", help="Run file/ffprobe verification after each download")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on the number of rows")
    parser.add_argument("--allow-non-tap", action="store_true", help="Allow non-TAP recordings as a final fallback")
    parser.add_argument("--skip-existing", action="store_true", help="Reuse an existing file if already present")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    session = None
    username = os.getenv(args.username_env, "").strip()
    password = os.getenv(args.password_env, "").strip()
    if username and password:
        session = _session_from_env(args.username_env, args.password_env)
        print("UCR login: OK")
    elif args.require_login:
        raise SystemExit(f"Missing UCR credentials in {args.username_env}/{args.password_env}")

    out = Path(args.output_root)
    raw_dir = ensure_dir(out / "raw")
    index_dir = ensure_dir(out / "index")
    index_csv = Path(args.index_csv) if args.index_csv else index_dir / "ucr_case_videos_with_fallback.csv"

    index_rows: list[dict[str, object]] = []
    for idx, src in enumerate(rows, start=1):
        record_id = (src.get(args.record_id_column) or src.get("sample_id") or f"record_{idx}").strip()
        case_name = (src.get(args.case_name_column) or src.get("case_name") or src.get("case_family") or "").strip()
        case_id = (src.get(args.case_id_column) or src.get("case_id") or "").strip()
        direct_url = (src.get(args.video_url_column) or src.get("video_url") or src.get("source_url") or "").strip()

        resolved_case_number = _resolve_case_number(case_name, case_id)
        chosen_title = ""
        chosen_date = ""
        resolved_video_url = ""
        local_path = ""
        download_status = "skipped"
        skip_reason = ""

        if _looks_like_direct_media_url(direct_url):
            resolved_video_url = direct_url
            chosen_title = "direct_media_url"
            skip_reason = ""
        elif not resolved_case_number:
            skip_reason = "no case number candidate available"
        else:
            case_desc = ""
            for allow_non_tap in (False, True):
                case_desc, docs, recordings, mode = _try_case(
                    session,
                    resolved_case_number,
                    title_contains=args.title_contains,
                    date=args.date,
                    index=args.index,
                    allow_non_tap=allow_non_tap and args.allow_non_tap,
                )
                if recordings:
                    chosen = recordings[max(args.index - 1, 0)]
                    raw_url = str(chosen.get("DocumentPath") or "").strip()
                    if raw_url:
                        resolved_video_url = _normalize_path(raw_url)
                        chosen_title = str(chosen.get("DocumentTitle") or case_desc or resolved_case_number)
                        chosen_date = str(chosen.get("DocSignatureDate") or "")
                        break
                    skip_reason = f"selected recording missing DocumentPath ({mode})"
                else:
                    skip_reason = mode
            if not resolved_video_url and not skip_reason:
                skip_reason = f"no downloadable recording for {resolved_case_number}"

        if resolved_video_url:
            suffix = Path(urlparse(resolved_video_url).path).suffix.lower() or ".mp4"
            if suffix not in DIRECT_MEDIA_SUFFIXES:
                suffix = ".mp4"
            case_slug = slugify(case_name or case_id or record_id)
            stem = safe_filename(
                resolved_video_url,
                f"{case_slug}_{chosen_date or 'tape'}_{sha1_short(resolved_video_url)}{suffix}",
            )
            if not Path(stem).suffix:
                stem = f"{stem}{suffix}"
            dest = raw_dir / case_slug / stem
            try:
                if args.skip_existing and dest.exists():
                    local_path = str(dest)
                    download_status = "exists"
                else:
                    _download(resolved_video_url, dest, session)
                    local_path = str(dest)
                    download_status = "downloaded"
                if args.verify and local_path:
                    verify_media(Path(local_path))
            except Exception as exc:
                download_status = "failed"
                skip_reason = f"{skip_reason}; {exc}".strip("; ")
                local_path = ""

        index_rows.append(
            {
                "sample_id": f"{slugify(case_name or 'ucr')}_{slugify(record_id)}_{sha1_short(resolved_video_url or record_id)}",
                "record_id": record_id,
                "case_name": case_name,
                "case_id": case_id,
                "resolved_case_number": resolved_case_number,
                "resolved_video_url": resolved_video_url,
                "chosen_title": chosen_title,
                "chosen_date": chosen_date,
                "local_video_path": local_path,
                "download_status": download_status,
                "skip_reason": skip_reason,
                "source_video_url": direct_url,
            }
        )
        print(
            f"row={idx} case_name={case_name!r} case_number={resolved_case_number or '(none)'} "
            f"status={download_status} reason={skip_reason or '(none)'}"
        )

    write_csv(
        index_csv,
        index_rows,
        [
            "sample_id",
            "record_id",
            "case_name",
            "case_id",
            "resolved_case_number",
            "resolved_video_url",
            "chosen_title",
            "chosen_date",
            "local_video_path",
            "download_status",
            "skip_reason",
            "source_video_url",
        ],
    )
    print(f"Wrote {len(index_rows)} fallback UCR rows to {index_csv}")


if __name__ == "__main__":
    main()
