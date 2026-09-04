"""Append one processed Tupac source to the visual-review manifest safely."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


VISUAL_DEFAULTS = {
    "speaker_face_match": "UNKNOWN",
    "target_witness_visible": "UNKNOWN",
    "target_witness_speaking": "UNKNOWN",
    "visual_speaker_match": "UNKNOWN",
    "speaker_visible_during_speech": "",
    "face_visible_ratio": "",
    "visual_verification_status": "UNREVIEWED",
    "visual_verification_confidence": "",
    "visual_reviewer": "",
    "visual_review_notes": "",
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--existing-csv", required=True)
    p.add_argument("--source-csv", required=True)
    p.add_argument("--output-csv", required=True)
    p.add_argument("--summary-json", required=True)
    p.add_argument("--source-id", required=True)
    p.add_argument("--min-seconds", type=float, default=0.8)
    p.add_argument("--max-seconds", type=float, default=30.0)
    args = p.parse_args()

    existing = pd.read_csv(args.existing_csv, dtype=str).fillna("")
    source = pd.read_csv(args.source_csv, dtype=str).fillna("")
    if "youtube_id" not in source.columns or "utterance_id" not in source.columns:
        raise SystemExit("Source CSV must contain youtube_id and utterance_id")
    if "youtube_id" in existing.columns and (existing["youtube_id"] == args.source_id).any():
        raise SystemExit(f"Source already exists in visual-review CSV: {args.source_id}")

    duration = pd.to_numeric(source.get("clip_duration_seconds", ""), errors="coerce")
    selected = source[
        source["youtube_id"].eq(args.source_id)
        & source.get("speaker_role", "").str.strip().str.lower().eq("witness")
        & source.get("witness_speaking_status", "").str.strip().str.upper().eq("SPEAKING")
        & source.get("corpus_exclusion_status", "").str.strip().str.upper().ne("EXCLUDE")
        & duration.ge(args.min_seconds)
        & duration.le(args.max_seconds)
    ].copy()
    for column, default in VISUAL_DEFAULTS.items():
        if column not in selected.columns:
            selected[column] = default

    overlap = set(existing.get("utterance_id", pd.Series(dtype=str))) & set(selected["utterance_id"])
    if overlap:
        raise SystemExit(f"Duplicate utterance IDs would be introduced: {sorted(overlap)[:5]}")

    columns = list(existing.columns)
    for column in selected.columns:
        if column not in columns:
            columns.append(column)
    existing = existing.reindex(columns=columns, fill_value="")
    selected = selected.reindex(columns=columns, fill_value="")
    output = pd.concat([existing, selected], ignore_index=True)
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)

    summary = {
        "existing_rows": int(len(existing)),
        "source_rows_input": int(len(source)),
        "source_rows_appended": int(len(selected)),
        "output_rows": int(len(output)),
        "source_id": args.source_id,
        "duration_range_seconds": [args.min_seconds, args.max_seconds],
        "output_csv": str(output_path),
        "notes": [
            "Only Witness/SPEAKING, non-excluded rows in the configured duration range were appended.",
            "New visual fields are initialized as UNKNOWN or UNREVIEWED.",
            "Manual visual verification is required before using the new rows as a visible-witness corpus.",
        ],
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
