"""Build Tupac train/dev/test manifests from manually reviewed emotion labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


BASIC_EMOTIONS = {"neutral", "anger", "disgust", "fear", "joy", "sadness", "surprise"}
STATUSES = {"CONFIRMED", "REJECTED", "DEFERRED", "UNREVIEWED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True, help="Completed Tupac reviewer CSV")
    parser.add_argument("--output-csv", required=True, help="Combined confirmed training manifest")
    parser.add_argument("--train-csv", required=True)
    parser.add_argument("--dev-csv", required=True)
    parser.add_argument("--test-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail unless every input row has CONFIRMED, REJECTED, or DEFERRED status.",
    )
    args = parser.parse_args()

    source = Path(args.input_csv)
    frame = pd.read_csv(source, dtype=str).fillna("")
    required = {"utterance_id", "human_basic_emotion", "human_basic_emotion_review_status", "split"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")
    if frame["utterance_id"].duplicated().any():
        raise SystemExit("Input contains duplicate utterance_id values")

    frame["human_basic_emotion_review_status"] = frame["human_basic_emotion_review_status"].str.strip().str.upper()
    invalid_status = sorted(set(frame["human_basic_emotion_review_status"]) - STATUSES)
    if invalid_status:
        raise SystemExit(f"Invalid review statuses: {invalid_status}; allowed={sorted(STATUSES)}")
    unreviewed = frame["human_basic_emotion_review_status"].eq("UNREVIEWED")
    if args.require_complete and unreviewed.any():
        raise SystemExit(f"{int(unreviewed.sum())} rows are still UNREVIEWED")

    confirmed = frame["human_basic_emotion_review_status"].eq("CONFIRMED")
    confirmed_labels = frame.loc[confirmed, "human_basic_emotion"].str.strip().str.lower()
    invalid_labels = sorted(set(confirmed_labels) - BASIC_EMOTIONS)
    blank_confirmed = int(confirmed_labels.eq("").sum())
    if invalid_labels or blank_confirmed:
        raise SystemExit(
            "Confirmed rows require a valid basic-emotion label; "
            f"invalid={invalid_labels}, blank_confirmed={blank_confirmed}"
        )

    output = frame.loc[confirmed].copy()
    # Preserve the source value before making the derived file loader-ready.
    output["original_emotion_label"] = output.get("emotion_label", "")
    output["original_emotion_label_source"] = output.get("emotion_label_source", "")
    output["training_label"] = output["human_basic_emotion"].str.strip().str.lower()
    output["training_label_source"] = "HUMAN_GOLD"
    output["training_label_status"] = "HUMAN_CONFIRMED"
    output["training_label_is_human_gold"] = "YES"
    output["training_label_review_required"] = "NO"
    # The Phase 2 loader expects emotion_label. This is done only in the
    # derived training output; the reviewer CSV remains untouched.
    output["emotion_label"] = output["training_label"]
    output["emotion_label_source"] = "human_basic_emotion_review"
    output["emotion_label_confidence"] = output["human_basic_emotion_confidence"]

    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)

    split_paths = {"train": Path(args.train_csv), "dev": Path(args.dev_csv), "test": Path(args.test_csv)}
    split_counts: dict[str, int] = {}
    for split, path in split_paths.items():
        split_rows = output[output["split"].str.strip().str.lower().eq(split)].copy()
        path.parent.mkdir(parents=True, exist_ok=True)
        split_rows.to_csv(path, index=False)
        split_counts[split] = len(split_rows)

    summary = {
        "input_csv": str(source),
        "output_csv": str(output_path),
        "train_csv": str(split_paths["train"]),
        "dev_csv": str(split_paths["dev"]),
        "test_csv": str(split_paths["test"]),
        "input_rows": len(frame),
        "confirmed_rows_written": len(output),
        "rejected_rows": int(frame["human_basic_emotion_review_status"].eq("REJECTED").sum()),
        "deferred_rows": int(frame["human_basic_emotion_review_status"].eq("DEFERRED").sum()),
        "unreviewed_rows": int(unreviewed.sum()),
        "split_counts": split_counts,
        "training_label_counts": output["training_label"].value_counts().to_dict(),
        "notes": [
            "Only CONFIRMED human_basic_emotion rows are included.",
            "The reviewer CSV is not modified.",
            "training_label is the common target field for training and fine-tuning.",
            "emotion_label is populated only in this derived loader-ready output.",
            "original_emotion_label and original_emotion_label_source preserve source provenance.",
            "Use a separately human-reviewed test manifest for final evaluation.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
