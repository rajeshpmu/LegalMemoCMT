from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import create_ucr_session, ensure_dir, safe_filename, sha1_short
else:
    from .common import create_ucr_session, ensure_dir, safe_filename, sha1_short


UCR_BASE = "https://ucr.irmct.org"


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
        return json.loads(raw)
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
            raise ValueError(f"Refusing HTML response for video URL: {url}")
        first = True
        with dest.open("wb") as out:
            for chunk in resp.iter_content(chunk_size=1024 * 128):
                if not chunk:
                    continue
                if first:
                    first = False
                    head = chunk.lstrip().lower()
                    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
                        raise ValueError(f"Refusing HTML payload for video URL: {url}")
                out.write(chunk)
    return dest


def verify_media(path: Path) -> None:
    subprocess.run(["file", str(path)], check=True)
    subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", str(path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download one UCR court recording MP4 for a case")
    parser.add_argument("--case-number", required=True, help="Example: IT-95-5/18")
    parser.add_argument("--output-dir", default="data/phase2/manual_videos", help="Where to save the MP4")
    parser.add_argument("--title-contains", default="video", help="Filter recording titles by substring")
    parser.add_argument("--date", default="", help="Optional exact tape date filter in DD/MM/YYYY")
    parser.add_argument("--index", type=int, default=1, help="1-based index among filtered recordings")
    parser.add_argument("--username-env", default="UCR_USERNAME", help="Environment variable containing the UCR email")
    parser.add_argument("--password-env", default="UCR_PASSWORD", help="Environment variable containing the UCR password")
    parser.add_argument("--verify", action="store_true", help="Run file/ffprobe verification after download")
    args = parser.parse_args()

    session = _session_from_env(args.username_env, args.password_env)
    if session is not None:
        print("UCR login: OK")

    detail = _decode_api_payload(_get_json(session, "/api/Summary/ByCaseDetail", {"CaseNumber": args.case_number}))
    if not detail:
        raise SystemExit(f"No case detail returned for {args.case_number}")
    case_desc = str(detail[0].get("CaseDescription") or args.case_number)

    docs_payload = _get_json(session, "/api/Summary/ByCaseDocsByLang", {"CaseNumber": args.case_number, "Lang": "EN"})
    docs = _decode_api_payload(docs_payload)
    tapes = [d for d in docs if str(d.get("DocumentType") or "").strip().upper() == "TAP"]
    if args.date.strip():
        tapes = [d for d in tapes if str(d.get("DocSignatureDate") or "").strip() == args.date.strip()]
    if args.title_contains.strip():
        needle = args.title_contains.strip().lower()
        tapes = [d for d in tapes if needle in str(d.get("DocumentTitle") or "").lower()]
    tapes = sorted(tapes, key=lambda d: str(d.get("DocumentTitle") or ""))

    if not tapes:
        print(f"No court recordings found for {args.case_number} after filtering.")
        return

    print(f"Case: {case_desc} ({args.case_number})")
    print("Available recordings:")
    for idx, tape in enumerate(tapes, start=1):
        print(
            f"{idx}. {tape.get('DocumentTitle')} | {tape.get('DocSignatureDate')} | {tape.get('Lang')} | {tape.get('DocumentPath')}"
        )

    chosen = tapes[max(args.index - 1, 0)]
    raw_url = str(chosen.get("DocumentPath") or "").strip()
    if not raw_url:
        raise SystemExit("Chosen recording has no DocumentPath")
    media_url = _normalize_path(raw_url)
    suffix = Path(urlparse(media_url).path).suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".webm", ".mov", ".mkv"}:
        suffix = ".mp4"

    output_dir = Path(args.output_dir)
    stem = safe_filename(f"{args.case_number}_{chosen.get('DocSignatureDate', '')}_{chosen.get('DocumentTitle', '')}", f"ucr_{sha1_short(media_url)}")
    dest = output_dir / f"{stem}{suffix}"
    print(f"Downloading: {media_url}")
    path = _download(media_url, dest, session)
    print(f"Saved to: {path}")

    if args.verify:
        verify_media(path)
        print("Verification: OK")


if __name__ == "__main__":
    main()
