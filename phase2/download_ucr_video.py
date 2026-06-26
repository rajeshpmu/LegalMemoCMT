from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import create_ucr_session, ensure_dir, safe_filename, sha1_short
else:
    from .common import create_ucr_session, ensure_dir, safe_filename, sha1_short


def download_video(url: str, dest: Path, *, session: requests.Session | None = None) -> Path:
    ensure_dir(dest.parent)
    headers = {"User-Agent": "LegalMemoCMT-Phase2/1.0 (+manual test downloader)"}
    getter = session.get if session is not None else requests.get
    with getter(url, headers=headers, timeout=120, stream=True, verify=True) as response:
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        if "text/html" in content_type or "application/xhtml+xml" in content_type:
            raise ValueError(f"Refusing HTML response for video URL: {url}")

        first_chunk = True
        with dest.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if not chunk:
                    continue
                if first_chunk:
                    first_chunk = False
                    head = chunk.lstrip().lower()
                    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
                        raise ValueError(f"Refusing HTML payload for video URL: {url}")
                out.write(chunk)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Download one direct UCR/IRMCT MP4 video link")
    parser.add_argument("--url", required=True, help="Direct mp4/webm/mov video URL copied from the UCR viewer")
    parser.add_argument("--output-dir", default="data/phase2/manual_videos", help="Directory where the video will be saved")
    parser.add_argument("--name", default="", help="Optional output filename stem")
    parser.add_argument("--username-env", type=str, default="UCR_USERNAME", help="Environment variable containing the UCR login email")
    parser.add_argument("--password-env", type=str, default="UCR_PASSWORD", help="Environment variable containing the UCR password")
    args = parser.parse_args()

    session = None
    username = os.getenv(args.username_env, "").strip()
    password = os.getenv(args.password_env, "").strip()
    if username and password:
        session = create_ucr_session(username, password)
        print("UCR login: OK")

    output_dir = Path(args.output_dir)
    stem = args.name.strip() or f"ucr_{sha1_short(args.url)}"
    suffix = Path(args.url.split("?", 1)[0]).suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".webm", ".mov", ".mkv"}:
        suffix = ".mp4"
    dest = output_dir / f"{safe_filename(stem, stem)}{suffix}"

    path = download_video(args.url, dest, session=session)
    print(path)


if __name__ == "__main__":
    main()
