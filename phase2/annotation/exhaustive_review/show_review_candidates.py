"""Pretty-print AI review candidates before human promotion."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from textwrap import shorten


def value(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--priority", choices=["HIGH", "MEDIUM", "LOW"], default="")
    parser.add_argument("--utterance-id", action="append", default=[])
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    wanted = set(args.utterance_id)
    selected = []
    for row in rows:
        if wanted and value(row, "utterance_id") not in wanted:
            continue
        if args.priority and value(row, "annotation_priority").upper() != args.priority:
            continue
        selected.append(row)
    if args.limit > 0:
        selected = selected[: args.limit]

    fields = [
        ("utterance_id", "Utterance ID"),
        ("youtube_id", "Source"),
        ("split", "Split"),
        ("start_time", "Start"),
        ("end_time", "End"),
        ("clip_duration_seconds", "Duration"),
        ("speaker_cluster_id", "Speaker cluster"),
        ("speaker_role", "Speaker role"),
        ("utterance_text", "Transcript"),
        ("phase1_basic_emotion", "Phase 1 emotion"),
        ("phase1_basic_emotion_confidence", "Phase 1 confidence"),
        ("audio_emotion_candidate", "SpeechBrain emotion"),
        ("audio_emotion_confidence", "SpeechBrain confidence"),
        ("audio_valence", "Odyssey valence"),
        ("audio_arousal", "Odyssey arousal"),
        ("audio_dominance", "Odyssey dominance"),
        ("deberta_target_scope", "DeBERTa target scope"),
        ("deberta_target_scope_confidence", "DeBERTa target confidence"),
        ("deberta_temporal_scope", "DeBERTa temporal scope"),
        ("modality_disagreement_score", "Modality disagreement"),
        ("semantic_leakage_risk", "Semantic leakage risk"),
        ("recommended_basic_emotion", "Recommended basic emotion"),
        ("recommended_basic_emotion_confidence", "Recommended basic confidence"),
        ("recommended_courtroom_affect", "Recommended courtroom affect"),
        ("recommended_courtroom_affect_confidence", "Recommended affect confidence"),
        ("recommended_affect_intensity", "Recommended intensity"),
        ("recommended_target_scope", "Recommended target scope"),
        ("recommended_temporal_scope", "Recommended temporal scope"),
        ("observable_cues", "Observable cue candidates"),
        ("domain_adaptation_pattern", "Domain adaptation pattern"),
        ("critical_conflict", "Critical conflict"),
        ("annotation_priority", "Priority"),
        ("review_reason", "Review rationale"),
        ("audio_review_status", "Audio review status"),
        ("visual_review_status", "Visual review status"),
        ("review_provenance", "Review provenance"),
        ("review_status", "Review status"),
        ("human_decision", "Human decision"),
    ]
    print(f"Rows shown: {len(selected)}")
    for index, row in enumerate(selected, 1):
        print(f"\n--- Candidate {index} ---")
        for key, label in fields:
            item = value(row, key) or "[blank]"
            if key == "utterance_text":
                item = shorten(" ".join(item.split()), width=600, placeholder=" ...")
            print(f"{label}: {item}")


if __name__ == "__main__":
    main()
