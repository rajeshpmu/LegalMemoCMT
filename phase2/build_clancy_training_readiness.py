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


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_training_manifest_weak.csv")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_training_readiness_summary.json")
DEFAULT_ISSUES = Path("reports/phase2/clancy_training_readiness_issues.csv")


def _nonempty(value: object) -> bool:
    return bool(str(value or "").strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Clancy weak-label training manifest for fine-tuning readiness")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--issues-csv", default=str(DEFAULT_ISSUES))
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    if not input_path.exists():
        raise SystemExit(f"Training manifest not found: {input_path}")

    rows = read_csv_rows(input_path)
    if not rows:
        raise SystemExit(f"Training manifest is empty: {input_path}")

    required_columns = {
        "utterance_id",
        "youtube_id",
        "split",
        "utterance_text",
        "audio_path",
        "video_path",
        "subtitle_path",
        "emotion_label",
        "emotion_label_source",
        "emotion_label_confidence",
        "review_flag",
    }
    columns = set(rows[0].keys())
    missing_columns = sorted(required_columns - columns)

    issues: list[dict[str, str]] = []
    utterance_counts = Counter()
    split_counts = Counter()
    label_counts = Counter()
    confidence_counts = Counter()
    youtube_splits: dict[str, set[str]] = defaultdict(set)
    review_counts = Counter()

    for row in rows:
        utterance_id = str(row.get("utterance_id", "")).strip()
        youtube_id = str(row.get("youtube_id", "")).strip()
        split = str(row.get("split", "")).strip().lower()
        label = str(row.get("emotion_label", "")).strip()
        confidence = str(row.get("emotion_label_confidence", "")).strip().upper()
        review_flag = str(row.get("review_flag", "")).strip().upper()

        utterance_counts[utterance_id] += 1
        split_counts[split] += 1
        label_counts[label] += 1
        confidence_counts[confidence] += 1
        review_counts[review_flag] += 1

        if youtube_id and split:
            youtube_splits[youtube_id].add(split)
        if not utterance_id:
            issues.append({"issue": "blank_utterance_id", "utterance_id": ""})
        if not _nonempty(row.get("utterance_text")):
            issues.append({"issue": "blank_utterance_text", "utterance_id": utterance_id})
        if not _nonempty(row.get("audio_path")):
            issues.append({"issue": "blank_audio_path", "utterance_id": utterance_id})
        if not _nonempty(row.get("video_path")):
            issues.append({"issue": "blank_video_path", "utterance_id": utterance_id})
        if not _nonempty(row.get("subtitle_path")):
            issues.append({"issue": "blank_subtitle_path", "utterance_id": utterance_id})
        if not label:
            issues.append({"issue": "blank_emotion_label", "utterance_id": utterance_id})
        if split not in {"train", "dev", "test"}:
            issues.append({"issue": "bad_split", "utterance_id": utterance_id, "value": split})
        if review_flag not in {"YES", "NO"}:
            issues.append({"issue": "bad_review_flag", "utterance_id": utterance_id, "value": review_flag})
        if confidence not in {"HIGH", "LOW", "MEDIUM", ""}:
            issues.append({"issue": "bad_confidence", "utterance_id": utterance_id, "value": confidence})

    for utterance_id, count in utterance_counts.items():
        if utterance_id and count > 1:
            issues.append({"issue": "duplicate_utterance_id", "utterance_id": utterance_id, "value": str(count)})
    for youtube_id, splits in youtube_splits.items():
        if len(splits) > 1:
            issues.append({"issue": "leakage_group_across_splits", "utterance_id": "", "value": youtube_id, "splits": ",".join(sorted(splits))})

    summary = {
        "input_csv": str(input_path),
        "total_rows": len(rows),
        "unique_utterance_ids": len([u for u in utterance_counts if u]),
        "split_counts": dict(sorted(split_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "review_flag_counts": dict(sorted(review_counts.items())),
        "missing_columns": missing_columns,
        "leakage_groups": [row for row in issues if row["issue"] == "leakage_group_across_splits"],
        "issues_count": len(issues),
        "ready_for_finetune": not missing_columns and not issues,
        "status": "PASS" if not missing_columns and not issues else "FAIL",
    }

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

    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
