from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir
    from phase2.dataset_builder import _infer_emotion_label
else:
    from .common import ensure_dir
    from .dataset_builder import _infer_emotion_label


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_dataset_manifest.csv")
DEFAULT_LABELS = Path("data/processed/phase2/clancy/clancy_weak_labels.csv")
DEFAULT_TRAINING = Path("data/processed/phase2/clancy/clancy_training_manifest_weak.csv")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_weak_label_summary.json")
DEFAULT_REVIEW = Path("reports/phase2/clancy_weak_label_review.csv")


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _confidence_for_label(label: str) -> str:
    return "HIGH" if label in {"anger", "fear", "sadness", "stress", "confidence"} else "LOW"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build weak emotion labels for the Clancy corpus")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--labels-csv", default=str(DEFAULT_LABELS))
    parser.add_argument("--training-csv", default=str(DEFAULT_TRAINING))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--review-csv", default=str(DEFAULT_REVIEW))
    parser.add_argument("--text-column", default="utterance_text")
    parser.add_argument("--id-column", default="utterance_id")
    parser.add_argument("--neutral-review-threshold", type=int, default=0)
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows: list[dict[str, str]] = []
    with input_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"No rows found in {input_path}")

    label_rows: list[dict[str, str]] = []
    training_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    label_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()

    for row in rows:
        utterance_id = _clean(row.get(args.id_column))
        text = _clean(row.get(args.text_column))
        if not utterance_id:
            continue
        emotion_label = _infer_emotion_label(text)
        label_source = "text_keyword_heuristic"
        confidence = _confidence_for_label(emotion_label)
        review_flag = "YES" if emotion_label != "neutral" or len(text) <= args.neutral_review_threshold else "NO"

        label_row = {
            "utterance_id": utterance_id,
            "emotion_label": emotion_label,
            "emotion_label_source": label_source,
            "emotion_label_confidence": confidence,
            "review_flag": review_flag,
            "review_reason": "keyword match" if emotion_label != "neutral" else "neutral default",
        }
        merged = dict(row)
        merged.update(label_row)
        training_rows.append(merged)
        label_rows.append(label_row)
        label_counts[emotion_label] += 1
        confidence_counts[confidence] += 1
        if review_flag == "YES":
            review_rows.append(merged)

    labels_path = Path(args.labels_csv)
    training_path = Path(args.training_csv)
    summary_path = Path(args.summary_json)
    review_path = Path(args.review_csv)
    for path in [labels_path, training_path, summary_path, review_path]:
        ensure_dir(path.parent)

    label_fieldnames = ["utterance_id", "emotion_label", "emotion_label_source", "emotion_label_confidence", "review_flag", "review_reason"]
    training_fieldnames = list(training_rows[0].keys())
    review_fieldnames = training_fieldnames

    with labels_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=label_fieldnames)
        writer.writeheader()
        writer.writerows(label_rows)

    with training_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=training_fieldnames)
        writer.writeheader()
        writer.writerows(training_rows)

    with review_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=review_fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)

    summary = {
        "input_csv": str(input_path),
        "labels_csv": str(labels_path),
        "training_csv": str(training_path),
        "review_csv": str(review_path),
        "total_rows": len(training_rows),
        "label_counts": dict(sorted(label_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "review_rows": len(review_rows),
        "status": "PASS",
        "notes": "Weak labels are generated from transparent transcript keyword rules and must be treated as provisional, not gold truth.",
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
