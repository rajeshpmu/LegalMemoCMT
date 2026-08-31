"""Recover conservative weak labels from multi-modal evidence.

The script is deliberately separate from the primary gate. It preserves all
input evidence, scores independent signals, and writes derived recovery fields
only. It does not create human gold labels or infer credibility/deception.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


AUDIO_MAP = {"neu": "neutral", "neutral": "neutral", "ang": "anger", "hap": "joy", "sad": "sadness"}
AUDIO_POLARITY = {"neu": "NEUTRAL", "neutral": "NEUTRAL", "ang": "NON_NEUTRAL", "hap": "NON_NEUTRAL", "sad": "NON_NEUTRAL"}
BEHAVIORAL_NON_NEUTRAL = {"TENSE", "DISTRESSED", "AGITATED", "DEFENSIVE", "HESITANT_UNCERTAIN"}
NON_SELF_SCOPES = {"OTHER_PERSON_DESCRIBED", "QUOTED_SPEECH"}


def text(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row.index:
            value = str(row[name]).strip()
            if value and value.lower() != "nan":
                return value
    return ""


def number(row: pd.Series, *names: str) -> float:
    try:
        return float(text(row, *names) or 0.0)
    except ValueError:
        return 0.0


def yes(row: pd.Series, *names: str) -> bool:
    return text(row, *names).upper() == "YES"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--non-neutral-threshold", type=float, default=4.0)
    parser.add_argument("--exact-class-threshold", type=float, default=6.0)
    parser.add_argument("--audio-confidence-threshold", type=float, default=0.80)
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if "utterance_id" not in df:
        raise SystemExit("Input manifest requires utterance_id")
    output = df.copy()
    defaults = {
        "recovery_evidence_score": "",
        "recovery_phase1_points": "",
        "recovery_audio_polarity_points": "",
        "recovery_exact_audio_points": "",
        "recovery_odyssey_points": "",
        "recovery_courtroom_affect_points": "",
        "recovery_visual_points": "",
        "recovery_penalty": "",
        "recovery_source_bucket": "",
        "recovery_decision": "WEAK_UNRESOLVED",
        "recovered_basic_emotion": "",
        "recovered_basic_emotion_confidence": "",
        "recovery_reason": "",
    }
    for column, default in defaults.items():
        if column not in output:
            output[column] = default

    counts = {"not_non_neutral": 0, "exact_class_silver": 0, "non_neutral_silver": 0, "weak_unresolved": 0}
    source_counts = {"LEVEL_1_ORIGINAL": 0, "WEAK_OR_CONFLICT": 0, "OTHER": 0}
    band_counts = {"<0.50": 0, "0.50-<0.65": 0, "0.65-<0.75": 0, "0.75-<0.85": 0, ">=0.85": 0}

    for index, row in output.iterrows():
        emotion = text(row, "phase1_basic_emotion", "phase1_candidate_emotion").lower()
        phase1_conf = number(row, "phase1_basic_emotion_confidence", "emotion_label_confidence")
        if not emotion or emotion == "neutral":
            output.at[index, "recovery_decision"] = "NOT_APPLICABLE"
            counts["not_non_neutral"] += 1
            continue

        if phase1_conf < 0.50:
            band = "<0.50"
        elif phase1_conf < 0.65:
            band = "0.50-<0.65"
        elif phase1_conf < 0.75:
            band = "0.65-<0.75"
        elif phase1_conf < 0.85:
            band = "0.75-<0.85"
        else:
            band = ">=0.85"
        band_counts[band] += 1

        phase1_points = 2 if phase1_conf >= 0.85 else (1 if phase1_conf >= 0.65 else 0)
        audio_code = text(row, "audio_emotion_candidate").lower()
        audio_label = AUDIO_MAP.get(audio_code, "")
        audio_conf = number(row, "audio_emotion_confidence")
        audio_polarity = AUDIO_POLARITY.get(audio_code, "")
        audio_polarity_points = 2 if audio_polarity == "NON_NEUTRAL" and audio_conf >= args.audio_confidence_threshold else 0
        exact_audio_points = 2 if audio_label == emotion and audio_conf >= args.audio_confidence_threshold else 0
        odyssey_points = 1 if text(row, "negative_activation_candidate").upper() == "YES" else 0
        affect_points = 1 if text(row, "proposed_courtroom_affect", "candidate_affect").upper() in BEHAVIORAL_NON_NEUTRAL else 0
        visual_points = 1 if yes(row, "visual_non_neutral_support") else 0

        target_scope = text(row, "deberta_target_scope", "emotion_target_scope").upper()
        target_conf = number(row, "deberta_target_scope_confidence", "target_scope_confidence")
        leakage = text(row, "semantic_leakage_risk").upper()
        speaker_evidence = text(row, "speaker_emotion_evidence_present").upper()
        penalty = 0
        blockers = []
        if leakage == "HIGH":
            penalty += 3
            blockers.append("high_semantic_leakage_risk")
        if target_scope in NON_SELF_SCOPES and target_conf >= 0.70 and speaker_evidence != "YES":
            penalty += 2
            blockers.append("high_confidence_non_self_emotion_scope")
        if text(row, "critical_conflict").upper() == "YES":
            blockers.append("critical_conflict")
        if text(row, "speaker_role").lower() not in {"", "witness"}:
            blockers.append("non_witness_speaker")
        if text(row, "witness_speaking_status").upper() not in {"", "SPEAKING"}:
            blockers.append("witness_not_speaking")

        score = phase1_points + audio_polarity_points + exact_audio_points + odyssey_points + affect_points + visual_points - penalty
        output.at[index, "recovery_evidence_score"] = f"{score:.2f}"
        output.at[index, "recovery_phase1_points"] = phase1_points
        output.at[index, "recovery_audio_polarity_points"] = audio_polarity_points
        output.at[index, "recovery_exact_audio_points"] = exact_audio_points
        output.at[index, "recovery_odyssey_points"] = odyssey_points
        output.at[index, "recovery_courtroom_affect_points"] = affect_points
        output.at[index, "recovery_visual_points"] = visual_points
        output.at[index, "recovery_penalty"] = penalty
        source_bucket = "LEVEL_1_ORIGINAL" if text(row, "non_neutral_promotion_route").startswith("LEVEL_1") else ("WEAK_OR_CONFLICT" if text(row, "non_neutral_annotation_status") == "UNRESOLVED" else "OTHER")
        output.at[index, "recovery_source_bucket"] = source_bucket
        source_counts[source_bucket] += 1

        if blockers:
            decision = "WEAK_UNRESOLVED"
            reason = "; ".join(blockers)
        elif score >= args.exact_class_threshold and exact_audio_points:
            decision = "EXACT_CLASS_SILVER"
            output.at[index, "recovered_basic_emotion"] = emotion
            output.at[index, "recovered_basic_emotion_confidence"] = f"{min(0.99, max(0.50, score / 8.0)):.6f}"
            reason = "multi-modal score >= exact threshold with comparable exact audio agreement"
        elif score >= args.non_neutral_threshold and audio_polarity_points:
            decision = "NON_NEUTRAL_SILVER"
            reason = "multi-modal score >= non-neutral threshold with independent non-neutral audio polarity"
        else:
            decision = "WEAK_UNRESOLVED"
            reason = "insufficient independent evidence for recovery"

        output.at[index, "recovery_decision"] = decision
        output.at[index, "recovery_reason"] = reason
        counts[{"EXACT_CLASS_SILVER": "exact_class_silver", "NON_NEUTRAL_SILVER": "non_neutral_silver"}.get(decision, "weak_unresolved")] += 1

    destination = Path(args.output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(output),
        "thresholds": {
            "non_neutral_score": args.non_neutral_threshold,
            "exact_class_score": args.exact_class_threshold,
            "audio_confidence": args.audio_confidence_threshold,
        },
        "decision_counts": counts,
        "source_bucket_counts": source_counts,
        "recovered_by_phase1_band": band_counts,
        "notes": [
            "This is a recovery experiment, not a human-labeling stage.",
            "Level 1 promotes non-neutral affect presence, not an exact emotion class.",
            "Level 2 requires comparable exact audio agreement in addition to the evidence score.",
            "NO_EMOTION_CONTENT is not itself a veto; high-confidence non-self emotional scope remains a leakage blocker.",
            "Visual evidence receives weight only from an explicit visual_non_neutral_support field; speaker visibility alone is not emotion evidence.",
            "No deception, credibility, truthfulness, or reliability label is inferred.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
