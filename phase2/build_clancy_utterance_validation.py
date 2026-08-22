from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows
else:
    from .common import read_csv_rows


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_utterance_manifest.csv")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_utterance_validation_summary.json")
DEFAULT_ISSUES = Path("reports/phase2/clancy_utterance_validation_issues.csv")

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _is_nonempty(value: object) -> bool:
    return bool(str(value or "").strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Clancy utterance manifest for traceability and uniqueness")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--issues-csv", default=str(DEFAULT_ISSUES))
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_csv_rows(input_path)

    duplicate_utterance_ids = [uid for uid, count in Counter(r.get("utterance_id", "") for r in rows).items() if uid and count > 1]
    composite_counts = Counter(
        (
            r.get("youtube_id", ""),
            r.get("cue_index", ""),
            r.get("start_time", ""),
            r.get("end_time", ""),
            r.get("utterance_text", ""),
        )
        for r in rows
    )
    duplicate_composites = [key for key, count in composite_counts.items() if count > 1]

    youtube_id_leaks = [r for r in rows if not YOUTUBE_ID_RE.match(str(r.get("youtube_id", "")).strip())]
    blank_source_url = [r for r in rows if not _is_nonempty(r.get("source_url"))]
    blank_video_path = [r for r in rows if not _is_nonempty(r.get("video_path"))]
    blank_audio_path = [r for r in rows if not _is_nonempty(r.get("audio_path"))]
    blank_subtitle_path = [r for r in rows if not _is_nonempty(r.get("subtitle_path"))]
    bad_utterance_prefix = [
        r
        for r in rows
        if _is_nonempty(r.get("youtube_id"))
        and not str(r.get("utterance_id", "")).startswith(f"{str(r.get('youtube_id')).strip()}_utt")
    ]

    issues: list[dict[str, object]] = []
    for uid in duplicate_utterance_ids:
        issues.append({"issue": "duplicate_utterance_id", "value": uid})
    for key in duplicate_composites:
        issues.append({"issue": "duplicate_utterance_composite", "value": "|".join(map(str, key))})
    for row in youtube_id_leaks[:50]:
        issues.append({"issue": "bad_youtube_id_format", "utterance_id": row.get("utterance_id"), "value": row.get("youtube_id")})
    for row in blank_source_url[:50]:
        issues.append({"issue": "blank_source_url", "utterance_id": row.get("utterance_id")})
    for row in blank_video_path[:50]:
        issues.append({"issue": "blank_video_path", "utterance_id": row.get("utterance_id")})
    for row in blank_audio_path[:50]:
        issues.append({"issue": "blank_audio_path", "utterance_id": row.get("utterance_id")})
    for row in blank_subtitle_path[:50]:
        issues.append({"issue": "blank_subtitle_path", "utterance_id": row.get("utterance_id")})
    for row in bad_utterance_prefix[:50]:
        issues.append(
            {
                "issue": "utterance_id_prefix_mismatch",
                "utterance_id": row.get("utterance_id"),
                "youtube_id": row.get("youtube_id"),
            }
        )

    issues_path = Path(args.issues_csv)
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    with issues_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["issue", "value", "utterance_id", "youtube_id"])
        writer.writeheader()
        for row in issues:
            writer.writerow(
                {
                    "issue": row.get("issue", ""),
                    "value": row.get("value", ""),
                    "utterance_id": row.get("utterance_id", ""),
                    "youtube_id": row.get("youtube_id", ""),
                }
            )

    summary = {
        "input_csv": str(input_path),
        "total_rows": len(rows),
        "unique_utterance_ids": len(set(r.get("utterance_id", "") for r in rows if _is_nonempty(r.get("utterance_id")))),
        "duplicate_utterance_ids": len(duplicate_utterance_ids),
        "duplicate_composite_rows": len(duplicate_composites),
        "bad_youtube_id_rows": len(youtube_id_leaks),
        "blank_source_url_rows": len(blank_source_url),
        "blank_video_path_rows": len(blank_video_path),
        "blank_audio_path_rows": len(blank_audio_path),
        "blank_subtitle_path_rows": len(blank_subtitle_path),
        "utterance_id_prefix_mismatch_rows": len(bad_utterance_prefix),
        "issues_csv": str(issues_path),
        "status": "PASS" if not issues else "FAIL",
        "notes": [
            "Duplicate utterance_text values are allowed because the same courtroom phrases can recur across a long trial.",
            "The validation checks exact row identity and traceability, not transcript-text uniqueness.",
        ],
    }

    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
