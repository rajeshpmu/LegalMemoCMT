"""Pretty-print Phase 1 and independent audio-SER results for one utterance."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def load_by_id(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row["utterance_id"]: row for row in csv.DictReader(handle) if row.get("utterance_id")}


def value(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip() or "[blank]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("utterance_id", help="Utterance ID to inspect")
    parser.add_argument(
        "--phase1-csv",
        default="data/processed/phase2/clancy/phase1_trimodal_pseudo_labels_200.csv",
    )
    parser.add_argument(
        "--audio-ser-csv",
        default="data/processed/phase2/clancy/audio_ser_evidence_200.csv",
    )
    args = parser.parse_args()

    phase1_path = Path(args.phase1_csv)
    audio_path = Path(args.audio_ser_csv)
    phase1 = load_by_id(phase1_path).get(args.utterance_id)
    audio = load_by_id(audio_path).get(args.utterance_id)
    if phase1 is None:
        raise SystemExit(f"Not found in Phase 1 manifest: {args.utterance_id}")
    if audio is None:
        raise SystemExit(f"Not found in audio-SER manifest: {args.utterance_id}")

    if value(phase1, "youtube_id") != value(audio, "youtube_id"):
        raise SystemExit(
            "Provenance mismatch: the utterance IDs match but youtube_id differs "
            f"({value(phase1, 'youtube_id')} vs {value(audio, 'youtube_id')})"
        )

    print(f"Utterance ID: {args.utterance_id}")
    print(f"Source: {value(phase1, 'youtube_id')}")
    print(f"Transcript: {value(phase1, 'utterance_text')}")
    print(f"Video: {value(phase1, 'clip_video_path')}")
    print(f"Audio: {value(phase1, 'clip_audio_path')}")

    print("\nPhase 1 Trimodal Prediction")
    for key, label in [
        ("phase1_basic_emotion", "Emotion"),
        ("phase1_basic_emotion_confidence", "Confidence"),
        ("phase1_basic_emotion_checkpoint", "Checkpoint"),
        ("phase1_basic_emotion_modalities", "Modalities"),
    ]:
        print(f"{label}: {value(phase1, key)}")

    print("\nOdyssey Audio-SER Evidence")
    for key, label in [
        ("audio_valence", "Valence"),
        ("audio_arousal", "Arousal"),
        ("audio_dominance", "Dominance"),
        ("audio_ser_odyssey_status", "Status"),
    ]:
        print(f"{label}: {value(audio, key)}")

    print("\nSpeechBrain Cross-check")
    for key, label in [
        ("audio_emotion_candidate", "Emotion candidate"),
        ("audio_emotion_confidence", "Confidence"),
        ("audio_emotion_model", "Model"),
        ("audio_ser_speechbrain_status", "Status"),
    ]:
        print(f"{label}: {value(audio, key)}")

    print("\nInterpretation: these are independent model signals; neither is a human-validated gold label.")


if __name__ == "__main__":
    main()
