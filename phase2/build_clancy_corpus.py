from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, sha1_short, slugify, write_csv
else:
    from .common import ensure_dir, sha1_short, slugify, write_csv


DEFAULT_URLS_FILE = Path("data/clancy_urls.txt")
DEFAULT_OUTPUT_ROOT = Path("data/phase2/clancy/corpus")
DEFAULT_MANIFEST_CSV = Path("data/processed/phase2/clancy/clancy_corpus_manifest.csv")
DEFAULT_SUMMARY_JSON = Path("reports/phase2/clancy_corpus_summary.json")
DEFAULT_FORMAT = "137+140/bestvideo*+bestaudio/best"


def _read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def _run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "check": True,
        "text": True,
    }
    if capture:
        kwargs["capture_output"] = True
    return subprocess.run(cmd, **kwargs)


def _yt_dlp_auth_args(
    cookies_from_browser: str | None,
    cookies_file: str | None,
    js_runtimes: str | None,
    remote_components: str | None,
) -> list[str]:
    args: list[str] = []
    if cookies_file:
        args += ["--cookies", cookies_file]
    elif cookies_from_browser:
        args += ["--cookies-from-browser", cookies_from_browser]
    if js_runtimes:
        args += ["--js-runtimes", js_runtimes]
    if remote_components:
        args += ["--remote-components", remote_components]
    return args


def _probe_metadata(
    url: str,
    *,
    ytdlp_bin: str,
    cookies_from_browser: str | None,
    cookies_file: str | None,
    js_runtimes: str | None,
    remote_components: str | None,
) -> dict[str, Any]:
    cmd = [ytdlp_bin, "--dump-single-json", "--no-playlist"]
    cmd += _yt_dlp_auth_args(cookies_from_browser, cookies_file, js_runtimes, remote_components)
    cmd.append(url)
    proc = _run(cmd, capture=True)
    try:
        return json.loads(proc.stdout)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Failed to parse yt-dlp metadata for {url}: {exc}") from exc


def _download_video(
    url: str,
    *,
    ytdlp_bin: str,
    output_template: str,
    format_string: str,
    cookies_from_browser: str | None,
    cookies_file: str | None,
    js_runtimes: str | None,
    remote_components: str | None,
    skip_existing: bool,
) -> None:
    cmd = [ytdlp_bin, "--no-playlist", "-f", format_string, "--merge-output-format", "mp4", "-o", output_template]
    if skip_existing:
        cmd.append("--no-overwrites")
    cmd += _yt_dlp_auth_args(cookies_from_browser, cookies_file, js_runtimes, remote_components)
    cmd.append(url)
    _run(cmd)


def _download_subtitles(
    url: str,
    *,
    ytdlp_bin: str,
    output_template: str,
    cookies_from_browser: str | None,
    cookies_file: str | None,
    js_runtimes: str | None,
    remote_components: str | None,
    skip_existing: bool,
    subtitle_langs: str,
) -> None:
    cmd = [
        ytdlp_bin,
        "--no-playlist",
        "--skip-download",
        "--write-auto-subs",
        "--sub-langs",
        subtitle_langs,
        "--sub-format",
        "vtt",
        "-o",
        output_template,
    ]
    if skip_existing:
        cmd.append("--no-overwrites")
    cmd += _yt_dlp_auth_args(cookies_from_browser, cookies_file, js_runtimes, remote_components)
    cmd.append(url)
    _run(cmd)


def _extract_audio(video_path: Path, wav_path: Path, *, ffmpeg_bin: str) -> None:
    ensure_dir(wav_path.parent)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    _run(cmd)


def _verify_media(path: Path) -> str:
    file_bin = shutil.which("file")
    ffprobe_bin = shutil.which("ffprobe")
    if file_bin is None:
        return "file command not available"
    proc = subprocess.run([file_bin, str(path)], check=True, text=True, capture_output=True)
    result = proc.stdout.strip()
    if ffprobe_bin:
        subprocess.run([ffprobe_bin, "-v", "error", "-show_streams", "-show_format", str(path)], check=True)
    else:
        result += "; ffprobe not found"
    return result


def _find_subtitle(base_stem: Path) -> Path | None:
    candidates = sorted(base_stem.parent.glob(base_stem.name + "*.vtt"))
    for candidate in candidates:
        return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a reusable Lindsay Clancy media corpus from YouTube URLs")
    parser.add_argument("--urls-file", default=str(DEFAULT_URLS_FILE), help="Text file containing one YouTube URL per line")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Directory for downloaded media")
    parser.add_argument("--manifest-csv", default=str(DEFAULT_MANIFEST_CSV), help="Output CSV manifest")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON), help="Output summary JSON")
    parser.add_argument("--ytdlp-bin", default="yt-dlp", help="yt-dlp executable")
    parser.add_argument("--ffmpeg-bin", default="ffmpeg", help="ffmpeg executable")
    parser.add_argument("--cookies-from-browser", default="chrome", help="Browser profile for yt-dlp cookies; use empty string to disable")
    parser.add_argument("--cookies-file", default="", help="Netscape-format cookies file; keep outside the repository")
    parser.add_argument("--js-runtimes", default="", help="yt-dlp JavaScript runtimes, for example deno:/usr/local/bin/deno")
    parser.add_argument("--remote-components", default="", help="yt-dlp remote components, for example ejs:github")
    parser.add_argument("--format-string", default=DEFAULT_FORMAT, help="yt-dlp format selector")
    parser.add_argument("--subtitle-langs", default="en", help="Subtitle language list for yt-dlp")
    parser.add_argument("--skip-existing", action="store_true", help="Reuse already downloaded files")
    parser.add_argument("--verify", action="store_true", help="Run file/ffprobe verification on downloaded media")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on the number of URLs processed")
    args = parser.parse_args()

    urls_file = Path(args.urls_file)
    if not urls_file.exists():
        raise SystemExit(f"URLs file not found: {urls_file}")

    urls = _read_urls(urls_file)
    if args.limit and args.limit > 0:
        urls = urls[: args.limit]
    if not urls:
        raise SystemExit(f"No URLs found in {urls_file}")

    if shutil.which(args.ytdlp_bin) is None:
        raise SystemExit(f"yt-dlp not found on PATH: {args.ytdlp_bin}")
    if shutil.which(args.ffmpeg_bin) is None:
        raise SystemExit(f"ffmpeg not found on PATH: {args.ffmpeg_bin}")

    output_root = Path(args.output_root)
    raw_root = ensure_dir(output_root / "raw")
    manifest_csv = Path(args.manifest_csv)
    summary_json = Path(args.summary_json)
    ensure_dir(manifest_csv.parent)
    ensure_dir(summary_json.parent)

    manifest_rows: list[dict[str, object]] = []
    summary: dict[str, object] = {
        "source_urls_file": str(urls_file),
        "output_root": str(output_root),
        "urls_total": len(urls),
        "videos_downloaded": 0,
        "videos_existing": 0,
        "videos_failed": 0,
        "audio_extracted": 0,
        "audio_existing": 0,
        "audio_failed": 0,
        "subtitles_downloaded": 0,
        "subtitles_existing": 0,
        "subtitles_failed": 0,
        "total_duration_minutes": 0.0,
    }

    cookies_from_browser = args.cookies_from_browser.strip() or None
    cookies_file = args.cookies_file.strip() or None
    if cookies_file and not Path(cookies_file).is_file():
        raise SystemExit(f"Cookies file not found: {cookies_file}")
    js_runtimes = args.js_runtimes.strip() or None
    remote_components = args.remote_components.strip() or None
    for row_num, url in enumerate(urls, start=1):
        meta: dict[str, Any] = {}
        title = ""
        video_id = ""
        duration_seconds = 0
        uploader = ""
        upload_date = ""
        base_stem = raw_root / "unknown" / f"clancy_{sha1_short(url)}"
        video_path = base_stem.with_suffix(".mp4")
        audio_path = base_stem.with_suffix(".wav")
        subtitle_path: Path | None = None
        video_status = "pending"
        audio_status = "pending"
        subtitle_status = "pending"
        notes: list[str] = []

        try:
            meta = _probe_metadata(
                url,
                ytdlp_bin=args.ytdlp_bin,
                cookies_from_browser=cookies_from_browser,
                cookies_file=cookies_file,
                js_runtimes=js_runtimes,
                remote_components=remote_components,
            )
            video_id = str(meta.get("id") or meta.get("display_id") or sha1_short(url))
            title = str(meta.get("title") or "")
            duration_seconds = int(meta.get("duration") or 0)
            uploader = str(meta.get("uploader") or meta.get("channel") or meta.get("creator") or "")
            upload_date = str(meta.get("upload_date") or "")
            corpus_slug = slugify(title or video_id or url, max_length=70)
            stem = f"{corpus_slug}_{video_id}"
            base_stem = raw_root / corpus_slug / stem
            video_path = base_stem.with_suffix(".mp4")
            audio_path = base_stem.with_suffix(".wav")
            subtitle_path = _find_subtitle(base_stem)
        except Exception as exc:
            notes.append(f"metadata_probe_failed={exc}")

        ensure_dir(base_stem.parent)

        try:
            if args.skip_existing and video_path.exists():
                video_status = "exists"
                summary["videos_existing"] = int(summary["videos_existing"]) + 1
            else:
                _download_video(
                    url,
                    ytdlp_bin=args.ytdlp_bin,
                    output_template=str(base_stem.with_suffix(".%(ext)s")),
                    format_string=args.format_string,
                    cookies_from_browser=cookies_from_browser,
                    cookies_file=cookies_file,
                    js_runtimes=js_runtimes,
                    remote_components=remote_components,
                    skip_existing=args.skip_existing,
                )
                video_status = "downloaded"
                summary["videos_downloaded"] = int(summary["videos_downloaded"]) + 1
        except Exception as exc:
            video_status = "failed"
            summary["videos_failed"] = int(summary["videos_failed"]) + 1
            notes.append(f"video_download_failed={exc}")

        if video_path.exists():
            try:
                if args.verify:
                    notes.append(f"video_verify={_verify_media(video_path)}")
                if args.skip_existing and audio_path.exists():
                    audio_status = "exists"
                    summary["audio_existing"] = int(summary["audio_existing"]) + 1
                else:
                    _extract_audio(video_path, audio_path, ffmpeg_bin=args.ffmpeg_bin)
                    audio_status = "extracted"
                    summary["audio_extracted"] = int(summary["audio_extracted"]) + 1
                if args.verify and audio_path.exists():
                    notes.append(f"audio_verify={_verify_media(audio_path)}")
            except Exception as exc:
                if audio_status != "exists":
                    audio_status = "failed"
                    summary["audio_failed"] = int(summary["audio_failed"]) + 1
                notes.append(f"audio_extract_failed={exc}")

        try:
            if args.skip_existing:
                existing_sub = _find_subtitle(base_stem)
                if existing_sub and existing_sub.exists():
                    subtitle_path = existing_sub
                    subtitle_status = "exists"
                    summary["subtitles_existing"] = int(summary["subtitles_existing"]) + 1
                else:
                    _download_subtitles(
                        url,
                        ytdlp_bin=args.ytdlp_bin,
                        output_template=str(base_stem.with_suffix(".%(ext)s")),
                        cookies_from_browser=cookies_from_browser,
                        cookies_file=cookies_file,
                        js_runtimes=js_runtimes,
                        remote_components=remote_components,
                        skip_existing=args.skip_existing,
                        subtitle_langs=args.subtitle_langs,
                    )
                    subtitle_path = _find_subtitle(base_stem)
                    subtitle_status = "downloaded" if subtitle_path and subtitle_path.exists() else "missing"
                    if subtitle_status == "downloaded":
                        summary["subtitles_downloaded"] = int(summary["subtitles_downloaded"]) + 1
            else:
                _download_subtitles(
                    url,
                    ytdlp_bin=args.ytdlp_bin,
                    output_template=str(base_stem.with_suffix(".%(ext)s")),
                    cookies_from_browser=cookies_from_browser,
                    cookies_file=cookies_file,
                    js_runtimes=js_runtimes,
                    remote_components=remote_components,
                    skip_existing=args.skip_existing,
                    subtitle_langs=args.subtitle_langs,
                )
                subtitle_path = _find_subtitle(base_stem)
                subtitle_status = "downloaded" if subtitle_path and subtitle_path.exists() else "missing"
                if subtitle_status == "downloaded":
                    summary["subtitles_downloaded"] = int(summary["subtitles_downloaded"]) + 1
        except Exception as exc:
            subtitle_status = "failed"
            summary["subtitles_failed"] = int(summary["subtitles_failed"]) + 1
            notes.append(f"subtitle_download_failed={exc}")

        if duration_seconds:
            summary["total_duration_minutes"] = round(float(summary["total_duration_minutes"]) + duration_seconds / 60.0, 3)

        manifest_rows.append(
            {
                "row_id": row_num,
                "source_url": url,
                "youtube_id": video_id,
                "title": title,
                "uploader": uploader,
                "upload_date": upload_date,
                "duration_seconds": duration_seconds,
                "video_path": str(video_path) if video_path.exists() else "",
                "audio_path": str(audio_path) if audio_path.exists() else "",
                "subtitle_path": str(subtitle_path) if subtitle_path and subtitle_path.exists() else "",
                "video_status": video_status,
                "audio_status": audio_status,
                "subtitle_status": subtitle_status,
                "media_verified": "YES" if args.verify and video_path.exists() and audio_path.exists() else "NO",
                "notes": "; ".join(notes),
            }
        )

        print(
            f"row={row_num} youtube_id={video_id or 'unknown'} "
            f"video={video_status} audio={audio_status} subtitles={subtitle_status}"
        )

    write_csv(
        manifest_csv,
        manifest_rows,
        [
            "row_id",
            "source_url",
            "youtube_id",
            "title",
            "uploader",
            "upload_date",
            "duration_seconds",
            "video_path",
            "audio_path",
            "subtitle_path",
            "video_status",
            "audio_status",
            "subtitle_status",
            "media_verified",
            "notes",
        ],
    )
    summary["manifest_csv"] = str(manifest_csv)
    summary["manifest_rows"] = len(manifest_rows)
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(manifest_rows)} Clancy corpus rows to {manifest_csv}")
    print(f"Wrote summary to {summary_json}")


if __name__ == "__main__":
    main()
