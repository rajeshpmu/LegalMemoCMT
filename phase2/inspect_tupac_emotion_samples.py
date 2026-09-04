"""Pretty-print a deterministic sample of every emotion in a Tupac manifest."""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path
from textwrap import shorten


def text(value: object) -> str:
    return str(value or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument(
        "--emotion-column",
        default="phase1_basic_emotion",
        help="Column containing the emotion to group by.",
    )
    parser.add_argument("--samples-per-emotion", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-confidence", type=float, default=None)
    parser.add_argument(
        "--min-duration",
        type=float,
        default=0.8,
        help="Minimum duration in seconds; rows below it are excluded as outliers.",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=30.0,
        help="Maximum duration in seconds; rows above it are excluded as outliers.",
    )
    parser.add_argument("--output-csv", default="", help="Optional sampled-row CSV.")
    args = parser.parse_args()

    if args.samples_per_emotion < 1:
        raise SystemExit("--samples-per-emotion must be at least 1")
    if args.min_duration < 0 or args.min_duration > args.max_duration:
        raise SystemExit("Duration bounds are invalid")

    input_path = Path(args.input_csv)
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"No rows found in {input_path}")
    if args.emotion_column not in rows[0]:
        raise SystemExit(f"Missing emotion column: {args.emotion_column}")

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    excluded_outliers = 0
    for row in rows:
        try:
            duration = float(text(row.get("clip_duration_seconds")))
        except ValueError:
            excluded_outliers += 1
            continue
        if duration < args.min_duration or duration > args.max_duration:
            excluded_outliers += 1
            continue
        emotion = text(row.get(args.emotion_column)).lower() or "[blank]"
        if args.min_confidence is not None:
            try:
                confidence = float(text(row.get("phase1_basic_emotion_confidence")))
            except ValueError:
                continue
            if confidence < args.min_confidence:
                continue
        groups[emotion].append(row)

    rng = random.Random(args.seed)
    selected: list[dict[str, str]] = []
    for emotion in sorted(groups):
        candidates = groups[emotion]
        sample = candidates if len(candidates) <= args.samples_per_emotion else rng.sample(candidates, args.samples_per_emotion)
        selected.extend(sample)

    if args.output_csv:
        output_path = Path(args.output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fields = list(rows[0])
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(selected)
        print(f"Sampled rows written to {output_path}")

    print(
        f"Input rows: {len(rows)} | Groups: {len(groups)} | "
        f"Selected rows: {len(selected)} | Outliers excluded: {excluded_outliers} | "
        f"Duration range: {args.min_duration:g}-{args.max_duration:g}s | "
        f"Samples per emotion: {args.samples_per_emotion} | Seed: {args.seed}"
    )
    display_fields = [
        ("utterance_id", "Utterance ID"),
        ("youtube_id", "Source"),
        ("split", "Split"),
        ("start_time", "Start"),
        ("end_time", "End"),
        ("clip_duration_seconds", "Duration (sec)"),
        ("speaker_cluster_id", "Speaker cluster"),
        ("speaker_role", "Speaker role"),
        ("phase1_basic_emotion", "Phase 1 emotion"),
        ("phase1_basic_emotion_confidence", "Phase 1 confidence"),
        ("audio_emotion_candidate", "SpeechBrain emotion"),
        ("audio_emotion_confidence", "SpeechBrain confidence"),
        ("audio_valence", "Odyssey valence"),
        ("audio_arousal", "Odyssey arousal"),
        ("audio_excitement", "Odyssey excitement alias"),
        ("audio_dominance", "Odyssey dominance"),
        ("semantic_emotion_present", "Semantic emotion present"),
        ("emotion_target_scope", "Original target scope"),
        ("auto_review_target_scope", "Auto-review target scope"),
        ("auto_review_temporal_scope", "Auto-review temporal scope"),
        ("auto_review_confidence", "Auto-review confidence"),
        ("auto_review_reason", "Auto-review reason"),
        ("deberta_target_scope", "DeBERTa target scope"),
        ("deberta_target_scope_confidence", "DeBERTa target confidence"),
        ("deberta_target_margin", "DeBERTa target margin"),
        ("deberta_temporal_scope", "DeBERTa temporal scope"),
        ("deberta_temporal_scope_confidence", "DeBERTa temporal confidence"),
        ("deberta_temporal_margin", "DeBERTa temporal margin"),
        ("emotion_temporal_scope", "Original temporal scope"),
        ("proposed_basic_emotion", "Proposed basic emotion"),
        ("proposed_basic_emotion_confidence", "Proposed basic confidence"),
        ("machine_proposed_basic_emotion", "Machine proposed emotion"),
        ("machine_proposed_basic_emotion_confidence", "Machine proposed confidence"),
        ("proposed_courtroom_affect", "Courtroom-affect candidate"),
        ("proposed_courtroom_affect_confidence", "Courtroom-affect confidence"),
        ("proposed_affect_intensity", "Proposed affect intensity"),
        ("courtroom_affect_evidence", "Courtroom-affect evidence"),
        ("courtroom_affect_missing_evidence", "Courtroom-affect missing evidence"),
        ("modality_disagreement_score", "Modality disagreement"),
        ("semantic_leakage_risk", "Semantic leakage risk"),
        ("annotation_priority", "Annotation priority"),
        ("critical_conflict", "Critical conflict"),
        ("annotation_status", "Annotation status"),
        ("annotation_tier", "Annotation tier"),
        ("human_review_required", "Human review required"),
        ("human_basic_emotion", "Human emotion"),
        ("human_basic_emotion_review_status", "Human review status"),
        ("clip_video_path", "Video clip"),
        ("clip_audio_path", "Audio clip"),
        ("utterance_text", "Transcript"),
    ]
    for emotion in sorted(groups):
        emotion_rows = [row for row in selected if text(row.get(args.emotion_column)).lower() == emotion]
        print(f"\n===== {emotion.upper()} ({len(groups[emotion])} available, {len(emotion_rows)} shown) =====")
        for index, row in enumerate(emotion_rows, 1):
            print(f"\n--- {emotion} sample {index} ---")
            for key, label in display_fields:
                value = text(row.get(key)) or "[blank]"
                if key == "utterance_text":
                    value = shorten(" ".join(value.split()), width=500, placeholder=" ...")
                print(f"{label}: {value}")


if __name__ == "__main__":
    main()
