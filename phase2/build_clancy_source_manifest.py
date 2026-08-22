from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir
else:
    from .common import ensure_dir


DEFAULT_URLS_FILE = Path("data/clancy_urls.txt")
DEFAULT_OUTPUT_CSV = Path("data/processed/phase2/clancy/clancy_source_manifest.csv")
DEFAULT_SUMMARY_JSON = Path("reports/phase2/clancy_source_manifest_summary.json")

KNOWN_ROWS: dict[str, dict[str, str]] = {
    "https://www.youtube.com/watch?v=sHUdRcABC-Q": {
        "youtube_id": "sHUdRcABC-Q",
        "title": "Psychiatrist Details Lindsay Clancy’s Hallucinations",
        "category": "psychiatrist_testimony",
        "priority": "5",
        "requested_label": "Dr. Sejal Shah – Psychiatrist testimony",
        "included": "YES",
    },
    "https://www.youtube.com/watch?v=ZJd1Lk4w-qo": {
        "youtube_id": "ZJd1Lk4w-qo",
        "title": "Dr. Alia Goodheart — Psychiatrist | Full Testimony | MA v. Lindsay Clancy",
        "category": "psychiatrist_full_testimony",
        "priority": "5",
        "requested_label": "Psychiatrist – Full Testimony",
        "included": "YES",
    },
    "https://www.youtube.com/watch?v=peYoD-JkAXE": {
        "youtube_id": "peYoD-JkAXE",
        "title": "Dr. Jennifer Tufts — Psychiatrist | Full Testimony | MA v. Lindsay Clancy",
        "category": "psychiatrist_full_testimony",
        "priority": "5",
        "requested_label": "Psychiatrist – Full Testimony",
        "included": "YES",
    },
    "https://www.youtube.com/watch?v=ma6ni-5zuW0": {
        "youtube_id": "ma6ni-5zuW0",
        "title": "Lindsay Clancy Trial: Lindsay's Mother Describes Her Daughter’s Anxiety, Insomnia & Depression |AB1E",
        "category": "family_testimony",
        "priority": "5",
        "requested_label": "Paula Musgrove – Lindsay's mother – Full Testimony",
        "included": "YES",
    },
    "https://www.youtube.com/watch?v=LGYerNiA8kI": {
        "youtube_id": "LGYerNiA8kI",
        "title": "Clancy Children's Pediatrician Testifies About Seeing Lindsay Hours Before Killings",
        "category": "pediatrician_testimony",
        "priority": "4",
        "requested_label": "Pediatrician testimony",
        "included": "YES",
    },
    "https://www.youtube.com/live/93sfJyLzhqM": {
        "youtube_id": "93sfJyLzhqM",
        "title": "LIVE: MA v. Lindsay Clancy - Day 8 | Accused Killer Mom Trial",
        "category": "full_trial_stream",
        "priority": "5",
        "requested_label": "Day 8 live trial",
        "included": "YES",
    },
    "https://www.youtube.com/live/D6skXbDJJj8": {
        "youtube_id": "D6skXbDJJj8",
        "title": "LIVE: Lindsay Clancy Murder Trial — MA v. Lindsay Clancy — Day 8",
        "category": "full_trial_stream",
        "priority": "5",
        "requested_label": "Day 8 live trial",
        "included": "YES",
    },
    "https://www.youtube.com/live/DCBWoWhsTpA": {
        "youtube_id": "DCBWoWhsTpA",
        "title": "LIVE: Lindsay Clancy trial Day 14",
        "category": "full_trial_stream",
        "priority": "5",
        "requested_label": "Day 14 full trial",
        "included": "YES",
    },
    "https://www.youtube.com/live/1tyKO8mTdOM": {
        "youtube_id": "1tyKO8mTdOM",
        "title": "LIVE: Lindsay Clancy trial Day 15",
        "category": "full_trial_stream",
        "priority": "5",
        "requested_label": "Day 15 full trial",
        "included": "YES",
    },
    "https://www.youtube.com/watch?v=D5L_c9Mla1U": {
        "youtube_id": "D5L_c9Mla1U",
        "title": "LIVE: Lindsay Clancy trial Day 16",
        "category": "full_trial_stream",
        "priority": "5",
        "requested_label": "Day 16 full trial",
        "included": "YES",
    },
    "https://www.youtube.com/watch?v=VQQb9BbgwHg": {
        "youtube_id": "VQQb9BbgwHg",
        "title": "LIVE: Lindsay Clancy trial Day 17",
        "category": "full_trial_stream",
        "priority": "5",
        "requested_label": "Day 17 full trial",
        "included": "YES",
    },
    "https://www.youtube.com/watch?v=ve9PzW4HfrY": {
        "youtube_id": "ve9PzW4HfrY",
        "title": "LIVE: MA v. Lindsay Clancy - Day 17 | Accused Killer Mom Trial 2026-08-20 21:53",
        "category": "full_trial_stream",
        "priority": "5",
        "requested_label": "Day 17 full trial",
        "included": "YES",
    },
}


def _read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def _probe_title(url: str, *, ytdlp_bin: str, cookies_from_browser: str | None) -> tuple[str, str]:
    cmd = [ytdlp_bin, "--no-playlist", "--get-id", "--get-title"]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    cmd.append(url)
    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    youtube_id = lines[0] if len(lines) > 0 else ""
    title = lines[1] if len(lines) > 1 else ""
    return youtube_id, title


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a small Clancy source manifest from the URL shortlist")
    parser.add_argument("--urls-file", default=str(DEFAULT_URLS_FILE))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--ytdlp-bin", default="yt-dlp")
    parser.add_argument("--cookies-from-browser", default="chrome")
    parser.add_argument("--skip-probe", action="store_true", help="Use the built-in title mapping only")
    args = parser.parse_args()

    urls_file = Path(args.urls_file)
    if not urls_file.exists():
        raise SystemExit(f"URLs file not found: {urls_file}")

    urls = _read_urls(urls_file)
    output_csv = Path(args.output_csv)
    summary_json = Path(args.summary_json)
    ensure_dir(output_csv.parent)
    ensure_dir(summary_json.parent)

    cookies_from_browser = args.cookies_from_browser.strip() or None
    rows: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    requested_counts: dict[str, int] = {}

    for idx, url in enumerate(urls, start=1):
        known = KNOWN_ROWS.get(url, {})
        youtube_id = known.get("youtube_id", "")
        title = known.get("title", "")
        if not args.skip_probe:
            try:
                probed_id, probed_title = _probe_title(url, ytdlp_bin=args.ytdlp_bin, cookies_from_browser=cookies_from_browser)
                youtube_id = probed_id or youtube_id
                title = probed_title or title
            except Exception:
                pass
        row = {
            "row_id": idx,
            "source_url": url,
            "youtube_id": youtube_id,
            "title": title,
            "category": known.get("category", "unknown"),
            "priority": known.get("priority", ""),
            "requested_label": known.get("requested_label", ""),
            "included_in_clancy_urls": known.get("included", "NO" if url not in KNOWN_ROWS else "YES"),
            "notes": "Exact URL is present in data/clancy_urls.txt" if url in KNOWN_ROWS else "URL present but not mapped in known shortlist",
        }
        rows.append(row)
        category = row["category"]
        category_counts[category] = category_counts.get(category, 0) + 1
        requested = row["requested_label"]
        if requested:
            requested_counts[requested] = requested_counts.get(requested, 0) + 1

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "row_id",
                "source_url",
                "youtube_id",
                "title",
                "category",
                "priority",
                "requested_label",
                "included_in_clancy_urls",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "source_urls_file": str(urls_file),
        "output_csv": str(output_csv),
        "rows": len(rows),
        "category_counts": category_counts,
        "requested_label_counts": requested_counts,
        "included_rows": sum(1 for row in rows if row["included_in_clancy_urls"] == "YES"),
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(rows)} Clancy source rows to {output_csv}")
    print(f"Wrote summary to {summary_json}")


if __name__ == "__main__":
    main()
