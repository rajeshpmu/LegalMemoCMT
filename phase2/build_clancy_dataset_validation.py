from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows
else:
    from .common import read_csv_rows


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_dataset_manifest.csv")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_dataset_validation_summary.json")
DEFAULT_ISSUES = Path("reports/phase2/clancy_dataset_validation_issues.csv")


def _nonempty(value: object) -> bool:
    return bool(str(value or "").strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Clancy split-aware dataset manifest")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--issues-csv", default=str(DEFAULT_ISSUES))
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.input_csv))
    issues: list[dict[str, object]] = []
    split_groups = defaultdict(set)
    utterance_ids = Counter()
    youtube_split = defaultdict(set)

    for row in rows:
        uid = row.get("utterance_id", "").strip()
        split = row.get("split", "").strip()
        group_id = row.get("split_group_id", "").strip()
        youtube_id = row.get("youtube_id", "").strip()
        utterance_ids[uid] += 1
        if split:
            split_groups[split].add(group_id)
        if youtube_id and split:
            youtube_split[youtube_id].add(split)
        if not _nonempty(row.get("source_url")):
            issues.append({"issue": "blank_source_url", "utterance_id": uid})
        if not _nonempty(row.get("video_path")):
            issues.append({"issue": "blank_video_path", "utterance_id": uid})
        if not _nonempty(row.get("audio_path")):
            issues.append({"issue": "blank_audio_path", "utterance_id": uid})
        if not _nonempty(row.get("subtitle_path")):
            issues.append({"issue": "blank_subtitle_path", "utterance_id": uid})
        if split not in {"train", "dev", "test"}:
            issues.append({"issue": "bad_split_value", "utterance_id": uid, "value": split})

    for uid, count in utterance_ids.items():
        if uid and count > 1:
            issues.append({"issue": "duplicate_utterance_id", "value": uid})
    for youtube_id, splits in youtube_split.items():
        if len(splits) > 1:
            issues.append({"issue": "leakage_group_across_splits", "value": youtube_id, "splits": ",".join(sorted(splits))})

    issues_path = Path(args.issues_csv)
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    with issues_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["issue", "utterance_id", "value", "splits"])
        writer.writeheader()
        for row in issues:
            writer.writerow(
                {
                    "issue": row.get("issue", ""),
                    "utterance_id": row.get("utterance_id", ""),
                    "value": row.get("value", ""),
                    "splits": row.get("splits", ""),
                }
            )

    split_counts = Counter(row.get("split", "") for row in rows)
    summary = {
        "input_csv": str(Path(args.input_csv)),
        "total_rows": len(rows),
        "unique_utterance_ids": len(utterance_ids),
        "split_counts": dict(split_counts),
        "split_group_counts": {split: len(groups) for split, groups in split_groups.items()},
        "leakage_groups": [row for row in issues if row["issue"] == "leakage_group_across_splits"],
        "issues_csv": str(issues_path),
        "status": "PASS" if not issues else "FAIL",
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
