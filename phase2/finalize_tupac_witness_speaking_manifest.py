"""Finalize manually reviewed Tupac witness-speaking rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--rejections-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--min-seconds", type=float, default=0.8)
    parser.add_argument("--max-seconds", type=float, default=30.0)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--notes", default="Manual review confirmed witness-speaking clips")
    args = parser.parse_args()

    source = Path(args.input_csv)
    df = pd.read_csv(source, dtype=str).fillna("")
    required = {"utterance_id", "youtube_id", "speaker_role", "witness_speaking_status", "clip_duration_seconds"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Input manifest missing columns: {missing}")

    duration = pd.to_numeric(df["clip_duration_seconds"], errors="coerce")
    eligible = (
        df["speaker_role"].str.strip().str.lower().eq("witness")
        & df["witness_speaking_status"].str.strip().str.upper().eq("SPEAKING")
        & df.get("corpus_exclusion_status", pd.Series("", index=df.index)).str.strip().str.upper().ne("EXCLUDE")
        & duration.ge(args.min_seconds)
        & duration.le(args.max_seconds)
    )
    selected = df.loc[eligible].copy()
    rejected = df.loc[~eligible].copy()

    duplicate_ids = int(selected["utterance_id"].duplicated().sum())
    if duplicate_ids:
        selected = selected.drop_duplicates("utterance_id", keep="first")

    for column, default in {
        "tupac_witness_speaking_validation_status": "HUMAN_VERIFIED",
        "tupac_witness_speaking_validation_source": "manual_clip_review",
        "tupac_witness_speaking_validation_confidence": "HIGH",
        "manual_review_status": "CONFIRMED",
        "manual_review_reviewer": args.reviewer,
        "manual_review_notes": args.notes,
    }.items():
        selected[column] = default
    selected["tupac_validated_witness_speaking"] = "YES"
    rejected["tupac_validated_witness_speaking"] = "NO"
    rejected["tupac_rejection_reason"] = rejected.apply(
        lambda row: "source_excluded"
        if str(row.get("corpus_exclusion_status", "")).upper() == "EXCLUDE"
        else "duration_outlier_or_invalid_witness_row",
        axis=1,
    )

    selected = selected.sort_values(["youtube_id", "clip_start_seconds", "utterance_id"], kind="stable")
    rejected = rejected.sort_values(["youtube_id", "clip_start_seconds", "utterance_id"], kind="stable")
    out = Path(args.output_csv)
    reject_out = Path(args.rejections_csv)
    summary_out = Path(args.summary_json)
    for path in (out, reject_out, summary_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(out, index=False)
    rejected.to_csv(reject_out, index=False)

    summary = {
        "input_csv": str(source),
        "output_csv": str(out),
        "rejections_csv": str(reject_out),
        "rows_input": int(len(df)),
        "rows_written": int(len(selected)),
        "rows_rejected": int(len(rejected)),
        "duplicate_utterance_ids_removed": duplicate_ids,
        "min_seconds": args.min_seconds,
        "max_seconds": args.max_seconds,
        "total_validated_minutes": round(float(pd.to_numeric(selected["clip_duration_seconds"], errors="coerce").sum()) / 60.0, 3),
        "source_count": int(selected["youtube_id"].nunique()),
        "review_status": "HUMAN_VERIFIED",
        "notes": [
            "Only Witness/SPEAKING rows within the configured duration range are selected.",
            "Excluded sources and duration outliers are preserved separately, not deleted.",
            "This manifest is ready for subsequent annotation and feature stages after validation.",
        ],
    }
    summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
