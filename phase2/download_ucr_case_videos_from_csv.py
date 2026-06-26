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
CASE_NUMBER_RE = re.compile(r"^[A-Z]{1,6}-[A-Z0-9-]+(?:/[A-Z0-9-]+)?$", re.IGNORECASE)

# Small fallback map for the case names already used in this repository.
# The CSV remains the primary driver; this only helps when a row carries a
# case name but no explicit UCR case number.
CASE_NAME_HINTS = {
    "karadzic": "IT-95-5/18",
    "mladic": "IT-09-92",
    "popovic": "IT-05-88",
    "akayesu": "ICTR-96-4-T",
    "bagosora": "ICTR-98-41-T",
}


def _session_from_env(username_env: str, password_env: str) -> requests.Session | None:
    username = os.getenv(username_env, "").strip()
    password = os.getenv(password_env, "").strip()
    if not username or not password:
        return None
    return create_ucr_session(username, password)


def _get_json(session: requests.Session | None, path: str, params: dict[str, str]) -> dict[str, object]:
    url = f"{UCR_BASE}{path}"
    getter = session.get if session is not None else requests.get
    resp = getter(url, params=params, timeout=60, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}, verify=True)
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


def _looks_like_direct_media_url(url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    return bool(url) and suffix in DIRECT_MEDIA_SUFFIXES


def _looks_like_case_number(text: str) -> bool:
    text = (text or "").strip()
    return bool(text) and bool(CASE_NUMBER_RE.match(text))


def _resolve_case_number(row: dict[str, str], *, case_id_column: str, case_name_column: str) -> str:
    candidate = (row.get(case_id_column) or row.get("case_number") or "").strip()
    if _looks_like_case_number(candidate):
        return candidate

    case_name = (row.get(case_name_column) or row.get("case_name") or "").strip()
    if _looks_like_case_number(case_name):
        return case_name

    hint_key = re.sub(r"[^a-z0-9]+", " ", case_name.lower()).strip()
    for key, case_number in CASE_NAME_HINTS.items():
        if key in hint_key:
            return case_number
    return ""


def _pick_tape(
    docs: list[dict[str, object]],
    *,
    title_contains: str,
    date: str,
    index: int,
) -> dict[str, object] | None:
    tapes = [d for d in docs if str(d.get("DocumentType") or "").strip().upper() == "TAP"]
    if date.strip():
        tapes = [d for d in tapes if str(d.get("DocSignatureDate") or "").strip() == date.strip()]
    if title_contains.strip():
        needle = title_contains.strip().lower()
        tapes = [d for d in tapes if needle in str(d.get("DocumentTitle") or "").lower()]
    tapes = sorted(tapes, key=lambda d: str(d.get("DocumentTitle") or ""))
    if not tapes:
        return None
    return tapes[max(index - 1, 0)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download UCR court recordings for cases listed in a CSV"
    )
    parser.add_argument("--source-csv", required=True, help="CSV with case_id, case_name, and optional direct URLs")
    parser.add_argument("--output-root", default="data/phase2/ucr_case_videos_from_csv", help="Where to store downloads")
    parser.add_argument("--index-csv", default="", help="Optional CSV path for the download index")
    parser.add_argument("--case-id-column", default="case_id", help="CSV column containing the case number or case identifier")
    parser.add_argument("--case-name-column", default="case_name", help="CSV column containing the human-readable case name")
    parser.add_argument("--record-id-column", default="record_id", help="CSV column used to derive a stable record identifier")
    parser.add_argument("--video-url-column", default="video_url", help="CSV column that may contain a direct media URL")
    parser.add_argument("--title-contains", default="video", help="Filter case recordings by title substring")
    parser.add_argument("--date", default="", help="Optional exact tape date filter in DD/MM/YYYY")
    parser.add_argument("--index", type=int, default=1, help="1-based index among filtered tapes")
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR password")
    parser.add_argument("--require-login", action="store_true", help="Fail if a UCR login cannot be established")
    parser.add_argument("--verify", action="store_true", help="Run file/ffprobe verification after each download")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on the number of CSV rows to process")
    parser.add_argument("--skip-existing", action="store_true", help="Reuse an existing local file if it is already present")
    args = parser.parse_args()

    source_rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        source_rows = source_rows[: args.limit]

    session = None
    username = os.getenv(args.username_env, "").strip()
    password = os.getenv(args.password_env, "").strip()
    if username and password:
        session = _session_from_env(args.username_env, args.password_env)
        print("UCR login: OK")
    elif args.require_login:
        raise SystemExit(
            f"Missing UCR credentials in environment variables {args.username_env} / {args.password_env}"
        )

    out = Path(args.output_root)
    raw_dir = ensure_dir(out / "raw")
    index_dir = ensure_dir(out / "index")
    index_csv = Path(args.index_csv) if args.index_csv else index_dir / "ucr_case_videos_from_csv.csv"

    download_cache: dict[tuple[str, str, str, int], str] = {}
    rows: list[dict[str, object]] = []

    for idx, src in enumerate(source_rows, start=1):
        record_id = (src.get(args.record_id_column) or src.get("sample_id") or f"record_{idx}").strip()
        case_name = (src.get(args.case_name_column) or src.get("case_name") or "").strip()
        case_id_raw = (src.get(args.case_id_column) or src.get("case_id") or "").strip()
        direct_url = (src.get(args.video_url_column) or src.get("video_url") or "").strip()
        court = (src.get("court") or src.get("tribunal") or "").strip()
        notes = (src.get("notes") or "").strip()

        resolved_case_number = _resolve_case_number(src, case_id_column=args.case_id_column, case_name_column=args.case_name_column)
        resolved_video_url = ""
        chosen_title = ""
        chosen_date = ""
        local_path = ""
        download_status = "skipped"
        message = ""

        if _looks_like_direct_media_url(direct_url):
            resolved_video_url = direct_url
            chosen_title = "direct_media_url"
            chosen_date = ""
        elif resolved_case_number:
            detail_payload = _decode_api_payload(
                _get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": resolved_case_number})
            )
            if detail_payload:
                case_desc = str(detail_payload[0].get("CaseDescription") or case_name or resolved_case_number)
            else:
                case_desc = case_name or resolved_case_number

            docs_payload = _get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": resolved_case_number, "Lang": "EN"})
            docs = _decode_api_payload(docs_payload)
            tape = _pick_tape(docs, title_contains=args.title_contains, date=args.date, index=args.index)
            if tape is None:
                message = f"no TAP recording matched case={resolved_case_number}"
            else:
                raw_url = str(tape.get("DocumentPath") or "").strip()
                if not raw_url:
                    message = f"selected tape has no DocumentPath for case={resolved_case_number}"
                else:
                    resolved_video_url = _normalize_path(raw_url)
                    chosen_title = str(tape.get("DocumentTitle") or case_desc or resolved_case_number)
                    chosen_date = str(tape.get("DocSignatureDate") or "")
        else:
            message = "no direct media url or usable case number in CSV row"

        if resolved_video_url:
            suffix = Path(urlparse(resolved_video_url).path).suffix.lower() or ".mp4"
            if suffix not in DIRECT_MEDIA_SUFFIXES:
                suffix = ".mp4"

            case_slug = slugify(case_name or case_id_raw or record_id)
            stem = safe_filename(
                resolved_video_url,
                f"{case_slug}_{chosen_date or 'tape'}_{sha1_short(resolved_video_url)}{suffix}",
            )
            if not Path(stem).suffix:
                stem = f"{stem}{suffix}"
            dest = raw_dir / case_slug / stem
            cache_key = (resolved_case_number or direct_url or record_id, chosen_title, chosen_date, args.index)
            if cache_key in download_cache:
                local_path = download_cache[cache_key]
                download_status = "cached"
            else:
                try:
                    if args.skip_existing and dest.exists():
                        local_path = str(dest)
                        download_status = "exists"
                    else:
                        _download(resolved_video_url, dest, session)
                        local_path = str(dest)
                        download_status = "downloaded"
                    download_cache[cache_key] = local_path
                    if args.verify and local_path:
                        verify_media(Path(local_path))
                except Exception as exc:
                    download_status = "failed"
                    message = f"{message}; {exc}".strip("; ")
                    local_path = ""

        rows.append(
            {
                "sample_id": f"{slugify(court or 'ucr')}_{slugify(record_id)}_{sha1_short(resolved_video_url or case_id_raw or record_id)}",
                "record_id": record_id,
                "case_id": case_id_raw,
                "case_name": case_name,
                "court": court,
                "resolved_case_number": resolved_case_number,
                "resolved_video_url": resolved_video_url,
                "chosen_title": chosen_title,
                "chosen_date": chosen_date,
                "local_video_path": local_path,
                "download_status": download_status,
                "message": message,
                "source_video_url": direct_url,
                "notes": notes,
            }
        )

    write_csv(
        index_csv,
        rows,
        [
            "sample_id",
            "record_id",
            "case_id",
            "case_name",
            "court",
            "resolved_case_number",
            "resolved_video_url",
            "chosen_title",
            "chosen_date",
            "local_video_path",
            "download_status",
            "message",
            "source_video_url",
            "notes",
        ],
    )
    print(f"Wrote {len(rows)} CSV-driven UCR case video rows to {index_csv}")


if __name__ == "__main__":
    main()
