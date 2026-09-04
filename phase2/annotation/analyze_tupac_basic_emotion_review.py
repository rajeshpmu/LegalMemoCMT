"""Generate evidence-based review suggestions and apply explicit Tupac reviews.

This script is a deterministic triage layer. It does not claim to replace human
audio/video inspection. Only the three explicitly reviewed examples below are
marked CONFIRMED; every other row keeps its existing review status.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


KNOWN_REVIEWS = {
    "lOcZ_IJbM3I_turn08614": {
        "emotion": "neutral",
        "confidence": "0.85",
        "affect": "ASSERTIVE",
        "affect_confidence": "0.75",
        "intensity": "1",
        "scope": "NO_EMOTION_CONTENT",
        "temporal": "NOT_APPLICABLE",
        "reason": "Phase 1 anger conflicts with no-emotion transcript semantics, neutral SpeechBrain output, and audiovisual review; delivery is assertive rather than angry.",
    },
    "DiurriBQxVs_turn00298": {
        "emotion": "neutral",
        "confidence": "0.90",
        "affect": "CALM_COMPOSED",
        "affect_confidence": "0.85",
        "intensity": "1",
        "scope": "NO_EMOTION_CONTENT",
        "temporal": "NOT_APPLICABLE",
        "reason": "Low-confidence Phase 1 anger conflicts with neutral SpeechBrain, low audio activation, high-confidence no-emotion scope, and audiovisual review of a stable factual response.",
    },
    "DiurriBQxVs_turn00281": {
        "emotion": "neutral",
        "confidence": "0.90",
        "affect": "CALM_COMPOSED",
        "affect_confidence": "0.85",
        "intensity": "1",
        "scope": "NO_EMOTION_CONTENT",
        "temporal": "NOT_APPLICABLE",
        "reason": "Phase 1 anger conflicts with no-emotion transcript semantics, neutral SpeechBrain, low audio activation, and audiovisual review; the response is corrective/confirmatory rather than angry.",
    },
}


def value(row: pd.Series, name: str) -> str:
    return str(row.get(name, "") or "").strip()


def number(row: pd.Series, name: str) -> float | None:
    try:
        return float(value(row, name))
    except ValueError:
        return None


def suggestion(row: pd.Series) -> tuple[str, str, str]:
    phase1 = value(row, "phase1_basic_emotion").lower()
    phase1_confidence = number(row, "phase1_basic_emotion_confidence") or 0.0
    audio = value(row, "audio_emotion_candidate").lower()
    audio_confidence = number(row, "audio_emotion_confidence") or 0.0
    target = value(row, "auto_review_target_scope") or value(row, "deberta_target_scope")
    target_confidence = number(row, "auto_review_confidence") or number(row, "deberta_target_scope_confidence") or 0.0
    arousal = number(row, "audio_arousal")
    if arousal is None:
        arousal = number(row, "audio_excitement")

    if target == "NO_EMOTION_CONTENT" and target_confidence >= 0.80:
        candidate = "neutral"
        reason = "high-confidence NO_EMOTION_CONTENT scope; do not attribute semantic emotion to the witness"
    elif phase1 == "neutral":
        candidate = "neutral"
        reason = "Phase 1 neutral candidate"
    elif audio in {"neu", "neutral"} and audio_confidence >= 0.80 and arousal is not None and arousal < 0.45:
        candidate = "neutral"
        reason = "neutral categorical audio evidence with low/moderate activation"
    else:
        candidate = phase1 or "UNRESOLVED"
        reason = "retain Phase 1 candidate pending human multimodal review"

    affect = value(row, "proposed_courtroom_affect") or "UNKNOWN"
    if affect == "UNKNOWN" and audio in {"neu", "neutral"} and arousal is not None and arousal < 0.45:
        affect = "CALM_COMPOSED"
    priority = "HIGH" if candidate != phase1 and phase1 else "MEDIUM" if candidate == "UNRESOLVED" else "LOW"
    reason = f"{reason}; phase1_confidence={phase1_confidence:.6f}"
    return candidate, affect, f"{priority}: {reason}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--reviewer", default="codex-session-review")
    parser.add_argument(
        "--apply-known-reviews",
        action="store_true",
        help="Apply only the three explicit reviewed records in this script.",
    )
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, dtype=str).fillna("")
    required = {"utterance_id", "phase1_basic_emotion", "phase1_basic_emotion_confidence"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")

    suggestion_values = frame.apply(suggestion, axis=1, result_type="expand")
    frame["codex_review_basic_emotion_candidate"] = suggestion_values[0]
    frame["codex_review_courtroom_affect_candidate"] = suggestion_values[1]
    frame["codex_review_priority"] = suggestion_values[2].str.split(":", n=1).str[0]
    frame["codex_review_reason"] = suggestion_values[2].str.split(": ", n=1).str[-1]
    frame["codex_review_status"] = "MACHINE_SUGGESTED"

    applied = []
    if args.apply_known_reviews:
        for index, row in frame.iterrows():
            review = KNOWN_REVIEWS.get(value(row, "utterance_id"))
            if not review:
                continue
            frame.at[index, "human_basic_emotion"] = review["emotion"]
            frame.at[index, "human_basic_emotion_review_status"] = "CONFIRMED"
            frame.at[index, "human_basic_emotion_confidence"] = review["confidence"]
            frame.at[index, "human_basic_emotion_reviewer"] = args.reviewer
            frame.at[index, "human_basic_emotion_notes"] = review["reason"]
            frame.at[index, "human_courtroom_affect"] = review["affect"]
            frame.at[index, "human_courtroom_affect_confidence"] = review["affect_confidence"]
            frame.at[index, "human_affect_intensity"] = review["intensity"]
            frame.at[index, "human_emotion_target_scope"] = review["scope"]
            frame.at[index, "human_emotion_temporal_scope"] = review["temporal"]
            frame.at[index, "human_review_reason"] = review["reason"]
            applied.append(value(row, "utterance_id"))

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    status_counts = frame.get("human_basic_emotion_review_status", pd.Series(dtype=str)).value_counts().to_dict()
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(frame),
        "known_reviews_available": sorted(KNOWN_REVIEWS),
        "known_reviews_applied": applied,
        "machine_suggestion_priority_counts": frame["codex_review_priority"].value_counts().to_dict(),
        "human_review_status_counts": status_counts,
        "notes": [
            "Codex-style analysis is deterministic machine-assisted triage, not automatic human review.",
            "Only explicitly supplied reviewed examples are marked CONFIRMED.",
            "All Phase 1, audio, scope, and existing human fields are preserved unless an explicit known review is applied.",
            "Review the remaining MACHINE_SUGGESTED rows manually before supervised training.",
            "No deception, credibility, truthfulness, or reliability label is inferred.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
