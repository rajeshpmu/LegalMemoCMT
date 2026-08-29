"""Inspect Clancy emotion-scope rows by annotation priority."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from textwrap import shorten


def clean(value: object) -> str:
    return str(value or "").strip() or "[blank]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--priority", choices=["HIGH", "MEDIUM", "LOW", "ALL"], default="HIGH")
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows written; 0 means no limit")
    parser.add_argument("--print-rows", type=int, default=10, help="Number of rows to pretty-print")
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    priority = args.priority.upper()
    selected = [row for row in rows if priority == "ALL" or clean(row.get("annotation_priority")) == priority]
    if args.limit > 0:
        selected = selected[: args.limit]

    output_path = Path(args.output_csv); output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(selected)

    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "requested_priority": priority,
        "input_rows": len(rows),
        "selected_rows": len(selected),
        "scope_counts": dict(Counter(clean(row.get("emotion_target_scope")) for row in selected)),
        "phase1_emotion_counts": dict(Counter(clean(row.get("phase1_basic_emotion")) for row in selected)),
        "proposed_emotion_counts": dict(Counter(clean(row.get("proposed_basic_emotion")) for row in selected)),
        "notes": [
            "Rows are review candidates, not automatically accepted labels.",
            "Inspect transcript, audio, video, and emotion target scope together.",
        ],
    }
    summary_path = Path(args.summary_json); summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.print_rows > 0:
        print(f"\nPretty-printing {min(args.print_rows, len(selected))} {priority} row(s):")
        fields_to_show = [
            ("utterance_id", "Utterance ID"),
            ("youtube_id", "Source"),
            ("split", "Split"),
            ("start_time", "Start"),
            ("end_time", "End"),
            ("clip_duration_seconds", "Duration (sec)"),
            ("phase1_basic_emotion", "Phase 1 emotion"),
            ("phase1_basic_emotion_confidence", "Phase 1 confidence"),
            ("audio_emotion_candidate", "SpeechBrain emotion"),
            ("audio_emotion_confidence", "SpeechBrain confidence"),
            ("audio_valence", "Odyssey valence"),
            ("audio_arousal", "Odyssey arousal"),
            ("audio_dominance", "Odyssey dominance"),
            ("emotion_target_scope", "Emotion target scope"),
            ("semantic_emotion_present", "Semantic emotion present"),
            ("semantic_leakage_risk", "Semantic leakage risk"),
            ("modality_disagreement_score", "Modality disagreement"),
            ("proposed_basic_emotion", "Proposed emotion"),
            ("proposed_basic_emotion_confidence", "Proposed confidence"),
            ("proposed_courtroom_affect", "Proposed courtroom affect"),
            ("review_reason", "Review reason"),
            ("utterance_text", "Transcript"),
            ("clip_video_path", "Video clip"),
            ("clip_audio_path", "Audio clip"),
        ]
        for index, row in enumerate(selected[: args.print_rows], 1):
            print(f"\n--- Row {index} ---")
            for key, label in fields_to_show:
                text = clean(row.get(key))
                if key == "utterance_text":
                    text = shorten(" ".join(text.split()), width=500, placeholder=" ...")
                print(f"{label}: {text}")


if __name__ == "__main__":
    main()
