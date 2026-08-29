"""Build conservative emotion-scope and disagreement review fields.

This is an auditable heuristic review layer. It does not create gold labels and
never overwrites Phase 1, audio-SER, or human annotation fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


EMOTION_TERMS = re.compile(
    r"\b(afraid|anxious|anger|angry|calm|cry|depress(?:ed|ion)|fear|felt|"
    r"frightened|happy|hopeless|hopelessness|joy|mood|numb|panic|sad|"
    r"suicid(?:al|e)|terrified|upset|worried)\b",
    re.IGNORECASE,
)
OTHER_PERSON = re.compile(
    r"\b(she|her|he|his|him|they|their|the patient|the victim|the child|"
    r"the defendant|the accused|my mother|my sister|my daughter|my son)\b",
    re.IGNORECASE,
)
QUOTED = re.compile(r"(?:\"[^\"]+\"|'[^']+'|\b(?:she|he|they)\s+(?:said|told|reported))", re.IGNORECASE)
EVENT_TERMS = re.compile(r"\b(the event|the incident|that day|what happened|the accident|the meeting)\b", re.IGNORECASE)


def clean(value: object) -> str:
    return str(value or "").strip()


def float_value(row: dict[str, str], key: str) -> float | None:
    try:
        return float(clean(row.get(key)))
    except (TypeError, ValueError):
        return None


def scope_for(text: str) -> tuple[str, str, bool]:
    has_emotion = bool(EMOTION_TERMS.search(text))
    if has_emotion and OTHER_PERSON.search(text):
        return "OTHER_PERSON_DESCRIBED", "emotion term occurs with other-person reference", True
    if QUOTED.search(text):
        return "QUOTED_SPEECH", "quote or reported speech marker", has_emotion
    if has_emotion and EVENT_TERMS.search(text):
        return "EVENT_DESCRIBED", "emotion term occurs in event-description context", True
    if has_emotion:
        return "SELF_EXPRESSED", "emotion term without detected external target", True
    return "UNCLEAR", "no explicit emotion-target evidence", False


def classify(row: dict[str, str], policy: str = "legacy") -> dict[str, str]:
    text = clean(row.get("utterance_text")) or clean(row.get("turn_text"))
    scope, scope_evidence, semantic_present = scope_for(text)
    phase1 = clean(row.get("phase1_basic_emotion")).lower()
    speech = clean(row.get("audio_emotion_candidate")).lower()
    arousal = float_value(row, "audio_arousal")
    valence = float_value(row, "audio_valence")
    confidence = float_value(row, "phase1_basic_emotion_confidence")

    # SpeechBrain has only neu/ang/hap/sad.  Map only its comparable classes;
    # absence of fear, disgust, and surprise is not evidence against those labels.
    audio_map = {"neu": "neutral", "neutral": "neutral", "ang": "anger", "hap": "joy", "sad": "sadness"}
    mapped_audio = audio_map.get(speech, "")
    categorical_disagreement = bool(phase1 and mapped_audio and phase1 != mapped_audio)
    scope_risk = scope == "OTHER_PERSON_DESCRIBED" and semantic_present
    acoustic_low_arousal = arousal is not None and arousal < 0.45
    audio_neutral = mapped_audio == "neutral"
    signals = []
    if categorical_disagreement:
        signals.append("phase1_vs_comparable_audio_disagreement")
    if scope_risk:
        signals.append("other_person_emotion_scope")
    if acoustic_low_arousal:
        signals.append("low_or_moderate_audio_arousal")
    if audio_neutral:
        signals.append("speechbrain_neutral")

    leakage = "HIGH" if scope_risk else "MEDIUM" if semantic_present else "LOW"
    if categorical_disagreement and scope_risk:
        disagreement = "HIGH"
    elif categorical_disagreement and confidence is not None and confidence >= 0.70 and float_value(row, "audio_emotion_confidence") is not None and float_value(row, "audio_emotion_confidence") >= 0.80:
        disagreement = "HIGH"
    elif categorical_disagreement or scope == "UNCLEAR" and semantic_present:
        disagreement = "MEDIUM"
    else:
        disagreement = "LOW"
    priority = "HIGH" if disagreement == "HIGH" else "MEDIUM" if disagreement == "MEDIUM" else "LOW"

    proposed = phase1 or "UNKNOWN"
    proposed_confidence = confidence if confidence is not None else 0.0
    outcome = "KEEP_PHASE1_CANDIDATE"
    reason = "comparable Phase 1 and audio categorical outputs agree or audio class is not comparable"
    proposed_affect = "UNKNOWN"
    proposed_intensity = ""
    visual_contrary = clean(row.get("speaker_visible_during_speech")).upper() == "NO"
    audio_failed = clean(row.get("audio_ser_status")).upper() in {"FAILED", "MISSING_AUDIO"}
    calm_supported = audio_neutral and acoustic_low_arousal and not visual_contrary and not audio_failed
    scope_supports_neutral = scope in {"OTHER_PERSON_DESCRIBED", "EVENT_DESCRIBED", "QUOTED_SPEECH"}
    if policy != "scope_aware" and scope_risk and audio_neutral and (arousal is None or arousal < 0.50):
        proposed = "neutral"
        proposed_confidence = 0.70
        outcome = "NEUTRAL_CANDIDATE"
        proposed_affect = "CALM_COMPOSED"
        proposed_intensity = "1"
        reason = "semantic content describes another person while audio evidence is neutral and low/moderate arousal"
    elif policy == "scope_aware" and calm_supported and scope_supports_neutral:
        proposed = "neutral"
        proposed_confidence = 0.72
        outcome = "NEUTRAL_CANDIDATE"
        proposed_affect = "CALM_COMPOSED"
        proposed_intensity = "1"
        reason = "calm courtroom presentation with neutral acoustic evidence, low/moderate arousal, and non-self emotion target"
    elif policy == "scope_aware" and calm_supported and scope == "SELF_EXPRESSED":
        proposed = "UNRESOLVED"
        proposed_confidence = 0.0
        outcome = "UNRESOLVED"
        reason = "calm low-arousal delivery does not exclude a self-expressed non-neutral emotion"
    elif policy == "scope_aware" and calm_supported and scope == "UNCLEAR":
        proposed = "neutral"
        proposed_confidence = 0.58
        outcome = "NEUTRAL_CANDIDATE"
        proposed_affect = "CALM_COMPOSED"
        proposed_intensity = "1"
        reason = "audio and courtroom-affect evidence support neutral, but emotion target is unresolved"
    elif policy == "legacy" and audio_neutral and acoustic_low_arousal and phase1 not in {"", "neutral"}:
        proposed = "neutral"
        proposed_confidence = 0.60
        outcome = "NEUTRAL_CANDIDATE"
        proposed_affect = "CALM_COMPOSED"
        proposed_intensity = "1"
        reason = "legacy review policy: non-neutral Phase 1 prediction conflicts with neutral low-arousal speech evidence"
    elif policy == "conservative" and categorical_disagreement:
        proposed = "UNRESOLVED"
        proposed_confidence = 0.0
        outcome = "UNRESOLVED"
        reason = "PHASE1_AUDIO_DISAGREEMENT_REQUIRES_MULTIMODAL_REVIEW"
    elif categorical_disagreement is False and phase1 and mapped_audio and phase1 == mapped_audio:
        reason = "PHASE1_AUDIO_AGREEMENT"

    out = {
        "semantic_emotion_present": "YES" if semantic_present else "NO",
        "emotion_target_scope": scope,
        "emotion_target_scope_evidence": scope_evidence,
        "modality_disagreement_score": disagreement,
        "semantic_leakage_risk": leakage,
        "annotation_priority": priority,
        "review_flag": "YES" if priority in {"HIGH", "MEDIUM"} else "NO",
        "review_reason": reason,
        "review_outcome": outcome,
        "phase1_candidate_emotion": phase1 or "UNKNOWN",
        "audio_candidate_emotion_mapped": mapped_audio or "NOT_COMPARABLE",
        "proposed_basic_emotion": proposed,
        "proposed_basic_emotion_confidence": f"{proposed_confidence:.6f}",
        "machine_proposed_basic_emotion": proposed,
        "machine_proposed_basic_emotion_confidence": f"{proposed_confidence:.6f}",
        "machine_proposal_basis": reason,
        "human_review_required": "YES" if priority in {"HIGH", "MEDIUM"} or outcome == "UNRESOLVED" else "NO",
        "proposed_courtroom_affect": proposed_affect,
        "proposed_affect_intensity": proposed_intensity,
        "scope_algorithm_signals": ";".join(signals),
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase1-csv", required=True)
    parser.add_argument("--audio-ser-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument(
        "--policy",
        choices=["legacy", "scope_aware", "conservative"],
        default="legacy",
        help="legacy proposes neutral for neutral low-arousal conflicts; conservative leaves ordinary conflicts unresolved",
    )
    args = parser.parse_args()

    with Path(args.phase1_csv).open(newline="", encoding="utf-8-sig") as handle:
        phase1_rows = list(csv.DictReader(handle))
    with Path(args.audio_ser_csv).open(newline="", encoding="utf-8-sig") as handle:
        audio_rows = {clean(row.get("utterance_id")): row for row in csv.DictReader(handle)}
    if args.max_rows > 0:
        phase1_rows = phase1_rows[: args.max_rows]

    output = []
    missing_audio = 0
    for phase1 in phase1_rows:
        key = clean(phase1.get("utterance_id"))
        audio = audio_rows.get(key, {})
        if not audio:
            missing_audio += 1
        if audio and clean(phase1.get("youtube_id")) != clean(audio.get("youtube_id")):
            raise SystemExit(f"Source mismatch for {key}: Phase 1 and audio-SER youtube_id differ")
        merged = dict(phase1)
        for field, value in audio.items():
            if field not in merged:
                merged[field] = value
        merged.update(classify(merged, args.policy))
        output.append(merged)

    out_path = Path(args.output_csv); out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output[0]) if output else []
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(output)
    summary = {
        "input_phase1_csv": args.phase1_csv,
        "input_audio_ser_csv": args.audio_ser_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(output),
        "policy": args.policy,
        "missing_audio_ser_rows": missing_audio,
        "scope_counts": dict(Counter(row["emotion_target_scope"] for row in output)),
        "disagreement_counts": dict(Counter(row["modality_disagreement_score"] for row in output)),
        "priority_counts": dict(Counter(row["annotation_priority"] for row in output)),
        "proposed_emotion_counts": dict(Counter(row["proposed_basic_emotion"] for row in output)),
        "notes": [
            "Proposed fields are conservative machine-review recommendations, not gold labels.",
            "Original Phase 1 and audio-SER fields are preserved.",
            "Human review is required for HIGH and MEDIUM priority rows before training.",
            "No deception, credibility, truthfulness, or reliability label is inferred.",
        ],
    }
    summary_path = Path(args.summary_json); summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
