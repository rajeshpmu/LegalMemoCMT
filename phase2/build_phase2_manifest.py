from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from .common import ensure_dir, group_case_splits, read_csv_rows, write_csv


REQUIRED_OUTPUT_COLUMNS = [
    "sample_id",
    "case_id",
    "court",
    "source_type",
    "language",
    "split",
    "label",
    "label_text",
    "confidence",
    "weak_rule",
    "transcript",
    "audio_path",
    "video_path",
    "raw_path",
    "transcript_path",
    "source_url",
    "notes",
]


def resolve_transcript(row: dict[str, str]) -> str:
    transcript = (row.get("transcript") or row.get("text") or "").strip()
    if transcript:
        return transcript
    transcript_path = (row.get("transcript_path") or row.get("text_path") or "").strip()
    if transcript_path and Path(transcript_path).exists():
        return Path(transcript_path).read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 2 manifests from public legal data sources")
    parser.add_argument(
        "--input-csv",
        type=str,
        nargs="+",
        required=True,
        help="One or more source index CSVs to merge",
    )
    parser.add_argument(
        "--weak-labels-csv",
        type=str,
        nargs="*",
        default=[],
        help="Optional one or more weak-label CSVs to merge by sample_id",
    )
    parser.add_argument("--output-dir", type=str, default="data/manifests/phase2", help="Manifest output directory")
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--dev-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--min-labeled-words",
        type=int,
        default=30,
        help="Skip rows shorter than this word-count threshold when forming labeled sets",
    )
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.output_dir))
    source_frames = [pd.read_csv(path) for path in args.input_csv]
    df = pd.concat(source_frames, ignore_index=True, sort=False)
    if df.empty:
        raise ValueError("No rows found in the supplied input CSVs")

    weak_lookup = {}
    for weak_path in args.weak_labels_csv:
        weak_df = pd.read_csv(weak_path)
        if "sample_id" not in weak_df.columns:
            raise ValueError(f"weak-label CSV must contain sample_id: {weak_path}")
        for _, row in weak_df.iterrows():
            weak_lookup[str(row["sample_id"])] = row.to_dict()

    if "case_id" not in df.columns:
        df["case_id"] = df["sample_id"]
    if "court" not in df.columns:
        df["court"] = "unknown"
    if "source_type" not in df.columns:
        df["source_type"] = "unknown"
    if "language" not in df.columns:
        df["language"] = "en"

    rows = df.to_dict(orient="records")
    case_map = group_case_splits(
        [str(row.get("case_id", row.get("sample_id", ""))) for row in rows],
        train_ratio=args.train_ratio,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
    )

    labeled_rows = []
    text_only_rows = []
    unlabeled_rows = []
    split_counts = Counter()
    label_counts = Counter()

    for row in rows:
        sample_id = str(row.get("sample_id", "")).strip()
        case_id = str(row.get("case_id", sample_id)).strip()
        split = str(row.get("split", "")).strip().lower() or case_map.get(case_id, "train")
        transcript = resolve_transcript({k: ("" if pd.isna(v) else str(v)) for k, v in row.items()})
        audio_path = str(row.get("audio_path", "") or "").strip()
        video_path = str(row.get("video_path", "") or "").strip()
        weak = weak_lookup.get(sample_id, {})
        label_val = weak.get("label", row.get("label", ""))
        label_text = weak.get("label_text", row.get("label_text", ""))
        confidence = weak.get("confidence", row.get("confidence", ""))
        weak_rule = weak.get("weak_rule", row.get("weak_rule", ""))

        cleaned = {
            "sample_id": sample_id,
            "case_id": case_id,
            "court": str(row.get("court", "")),
            "source_type": str(row.get("source_type", "")),
            "language": str(row.get("language", "en")),
            "split": split,
            "label": "" if pd.isna(label_val) else str(label_val),
            "label_text": "" if pd.isna(label_text) else str(label_text),
            "confidence": "" if pd.isna(confidence) else str(confidence),
            "weak_rule": "" if pd.isna(weak_rule) else str(weak_rule),
            "transcript": transcript,
            "audio_path": audio_path,
            "video_path": video_path,
            "raw_path": str(row.get("raw_path", "") or ""),
            "transcript_path": str(row.get("transcript_path", "") or ""),
            "source_url": str(row.get("source_url", "") or ""),
            "notes": str(row.get("notes", "") or ""),
        }

        has_label = bool(str(cleaned["label"]).strip())
        has_multimodal = bool(audio_path or video_path)
        split_counts[split] += 1

        if has_label:
            try:
                label_counts[int(float(cleaned["label"]))] += 1
            except Exception:
                pass

        if has_label and len(transcript.split()) >= args.min_labeled_words and has_multimodal:
            labeled_rows.append(cleaned)
        elif has_label and len(transcript.split()) >= args.min_labeled_words:
            text_only_rows.append(cleaned)
        else:
            unlabeled_rows.append(cleaned)

    write_csv(out_dir / "phase2_labeled_multimodal.csv", labeled_rows, REQUIRED_OUTPUT_COLUMNS)
    write_csv(out_dir / "phase2_labeled_text_only.csv", text_only_rows, REQUIRED_OUTPUT_COLUMNS)
    write_csv(out_dir / "phase2_unlabeled_corpus.csv", unlabeled_rows, REQUIRED_OUTPUT_COLUMNS)

    summary = {
        "total_rows": len(rows),
        "labeled_multimodal_rows": len(labeled_rows),
        "labeled_text_only_rows": len(text_only_rows),
        "unlabeled_rows": len(unlabeled_rows),
        "split_counts": dict(split_counts),
        "label_counts": dict(label_counts),
        "output_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
