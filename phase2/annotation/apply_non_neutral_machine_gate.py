"""Gate non-neutral Phase 1 candidates using tiered independent evidence.

This creates machine-assisted silver candidates only. It does not claim human
review and does not overwrite the original Phase 1 prediction. Strong Phase 1
rows do not require SpeechBrain agreement; moderate rows do.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


AUDIO_MAP = {"neu": "neutral", "neutral": "neutral", "ang": "anger", "hap": "joy", "sad": "sadness"}
AUDIO_POLARITY = {"neu": "NEUTRAL", "neutral": "NEUTRAL", "ang": "NON_NEUTRAL", "hap": "NON_NEUTRAL", "sad": "NON_NEUTRAL"}


def value(row: pd.Series, *columns: str) -> str:
    for column in columns:
        if column in row.index:
            item = str(row[column]).strip()
            if item and item.lower() != "nan":
                return item
    return ""


def number(row: pd.Series, *columns: str) -> float:
    try:
        return float(value(row, *columns) or 0.0)
    except ValueError:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--weak-threshold", type=float, default=0.65)
    parser.add_argument("--strong-threshold", type=float, default=0.85)
    parser.add_argument("--audio-corroboration-threshold", type=float, default=0.80)
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if "utterance_id" not in df:
        raise SystemExit("Input manifest requires utterance_id")

    output = df.copy()
    defaults = {
        "non_neutral_confidence_band": "",
        "independent_corroboration": "NO",
        "non_neutral_promotion_route": "",
        "audio_polarity": "",
        "audio_polarity_confidence": "",
        "machine_affect_presence": "UNRESOLVED",
        "machine_affect_presence_status": "UNRESOLVED",
        "machine_affect_presence_tier": "WEAK",
        "machine_final_basic_emotion": "",
        "machine_final_basic_emotion_confidence": "",
        "machine_final_basic_emotion_status": "UNRESOLVED",
        "machine_final_basic_emotion_tier": "WEAK",
        "non_neutral_final_basic_emotion": "",
        "non_neutral_final_basic_emotion_confidence": "",
        "non_neutral_annotation_status": "UNRESOLVED",
        "non_neutral_annotation_tier": "WEAK",
        "non_neutral_critical_conflict": "YES",
        "non_neutral_human_review_required": "YES",
        "non_neutral_gate_reason": "",
        "audio_excitement_alias_of_arousal": "YES",
    }
    for column, default in defaults.items():
        if column not in output:
            output[column] = default

    counts = {
        "not_non_neutral": 0,
        "unresolved_weak_confidence": 0,
        "unresolved_conflict": 0,
        "level1_affect_presence": 0,
        "level2_exact_class": 0,
    }
    for index, row in output.iterrows():
        emotion = value(row, "phase1_basic_emotion", "phase1_candidate_emotion").lower()
        phase1_conf = number(row, "phase1_basic_emotion_confidence", "emotion_label_confidence")
        if not emotion or emotion == "neutral":
            output.at[index, "non_neutral_confidence_band"] = "NOT_NON_NEUTRAL"
            output.at[index, "non_neutral_annotation_status"] = "NOT_APPLICABLE"
            output.at[index, "non_neutral_annotation_tier"] = "NOT_APPLICABLE"
            output.at[index, "non_neutral_critical_conflict"] = "NO"
            output.at[index, "non_neutral_human_review_required"] = "NO"
            counts["not_non_neutral"] += 1
            continue

        if phase1_conf < args.weak_threshold:
            band = "BELOW_0.65_WEAK"
        elif phase1_conf < args.strong_threshold:
            band = "0.65_TO_0.85_CORROBORATION_REQUIRED"
        else:
            band = "AT_OR_ABOVE_0.85_STRONG_CHECKS"
        output.at[index, "non_neutral_confidence_band"] = band

        audio_code = value(row, "audio_emotion_candidate").lower()
        audio_label = AUDIO_MAP.get(audio_code, "")
        audio_polarity = AUDIO_POLARITY.get(audio_code, "")
        audio_conf = number(row, "audio_emotion_confidence")
        corroborated = bool(audio_label and audio_label == emotion and audio_conf >= args.audio_corroboration_threshold)
        polarity_supported = bool(audio_polarity == "NON_NEUTRAL" and audio_conf >= args.audio_corroboration_threshold)
        output.at[index, "independent_corroboration"] = "YES" if corroborated else "NO"
        output.at[index, "audio_polarity"] = audio_polarity
        output.at[index, "audio_polarity_confidence"] = f"{audio_conf:.6f}" if audio_polarity else ""

        conflict_reasons = []
        if value(row, "semantic_leakage_risk").upper() == "HIGH":
            conflict_reasons.append("high_semantic_leakage_risk")
        if value(row, "critical_conflict").upper() == "YES":
            conflict_reasons.append("existing_critical_conflict")
        target_scope = value(row, "deberta_target_scope", "emotion_target_scope").upper()
        target_scope_conf = number(row, "deberta_target_scope_confidence", "target_scope_confidence")
        speaker_emotion_evidence = value(row, "speaker_emotion_evidence_present").upper()
        # Scope describes whose emotion the text discusses; it does not decide
        # whether the current witness is visibly or vocally emotional.
        if (
            target_scope in {"OTHER_PERSON_DESCRIBED", "QUOTED_SPEECH"}
            and target_scope_conf >= 0.70
            and speaker_emotion_evidence != "YES"
        ):
            conflict_reasons.append("high_confidence_non_self_emotion_scope")
        if value(row, "speaker_role").lower() and value(row, "speaker_role").lower() != "witness":
            conflict_reasons.append("non_witness_speaker")
        if value(row, "witness_speaking_status").upper() and value(row, "witness_speaking_status").upper() != "SPEAKING":
            conflict_reasons.append("witness_not_speaking")
        if value(row, "audio_ser_status").upper() in {"FAILED", "MISSING_AUDIO"}:
            conflict_reasons.append("audio_not_valid")

        if band == "BELOW_0.65_WEAK":
            counts["unresolved_weak_confidence"] += 1
            output.at[index, "non_neutral_promotion_route"] = "ROUTE_C_WEAK"
            reason = "Phase 1 non-neutral confidence below 0.65"
        elif conflict_reasons:
            counts["unresolved_conflict"] += 1
            output.at[index, "non_neutral_promotion_route"] = "UNRESOLVED_CONFLICT"
            reason = "; ".join(conflict_reasons)
        elif phase1_conf < args.strong_threshold:
            counts["unresolved_conflict"] += 1
            output.at[index, "non_neutral_promotion_route"] = "UNRESOLVED_CONFLICT"
            reason = "Level 1 requires Phase 1 confidence >= 0.85"
        elif not polarity_supported:
            counts["unresolved_conflict"] += 1
            output.at[index, "non_neutral_promotion_route"] = "UNRESOLVED_CONFLICT"
            reason = "Level 1 requires independent non-neutral audio polarity evidence"
        else:
            # Level 1 separates affect presence from exact emotion identity.
            output.at[index, "machine_affect_presence"] = "NON_NEUTRAL"
            output.at[index, "machine_affect_presence_status"] = "AUTO_ADJUDICATED"
            output.at[index, "machine_affect_presence_tier"] = "SILVER"
            output.at[index, "non_neutral_final_basic_emotion"] = emotion
            output.at[index, "non_neutral_final_basic_emotion_confidence"] = f"{phase1_conf:.6f}"
            output.at[index, "non_neutral_annotation_status"] = "AUTO_ADJUDICATED"
            output.at[index, "non_neutral_annotation_tier"] = "SILVER"
            output.at[index, "non_neutral_critical_conflict"] = "NO"
            output.at[index, "non_neutral_human_review_required"] = "NO"
            if corroborated:
                counts["level2_exact_class"] += 1
                output.at[index, "non_neutral_promotion_route"] = "LEVEL_2_EXACT_CLASS"
                output.at[index, "machine_final_basic_emotion"] = emotion
                output.at[index, "machine_final_basic_emotion_confidence"] = f"{phase1_conf:.6f}"
                output.at[index, "machine_final_basic_emotion_status"] = "AUTO_ADJUDICATED"
                output.at[index, "machine_final_basic_emotion_tier"] = "SILVER"
                reason = "Level 2: strong Phase 1 class with comparable exact audio agreement and no blocking conflict"
            else:
                counts["level1_affect_presence"] += 1
                output.at[index, "non_neutral_promotion_route"] = "LEVEL_1_AFFECT_PRESENCE"
                # A polarity match is enough to support non-neutral presence,
                # but not enough to overwrite the exact Phase 1 class.
                output.at[index, "non_neutral_final_basic_emotion"] = ""
                output.at[index, "non_neutral_final_basic_emotion_confidence"] = ""
                output.at[index, "non_neutral_annotation_status"] = "AUTO_ADJUDICATED"
                output.at[index, "non_neutral_annotation_tier"] = "SILVER"
                reason = "Level 1: strong Phase 1 non-neutral prediction with independent non-neutral audio polarity; exact class remains unresolved"
        output.at[index, "non_neutral_gate_reason"] = reason

    destination = Path(args.output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(output),
        "weak_threshold": args.weak_threshold,
        "strong_threshold": args.strong_threshold,
        "audio_corroboration_threshold": args.audio_corroboration_threshold,
        "counts": counts,
        "silver_rows": int((output["non_neutral_annotation_status"] == "AUTO_ADJUDICATED").sum()),
        "notes": [
            "Non-neutral confidence below 0.65 remains WEAK/UNRESOLVED.",
            "Level 1 requires Phase 1 confidence >= 0.85 plus independent non-neutral audio polarity; it does not claim an exact class.",
            "Level 2 requires comparable SpeechBrain class agreement at the configured confidence in addition to Level 1 checks.",
            "SpeechBrain polarity groups ang, hap, and sad as NON_NEUTRAL and neu as NEUTRAL; this is not exact-class agreement.",
            "Fear, disgust, and surprise can receive Level 1 polarity support without pretending SpeechBrain has those exact classes.",
            "audio_arousal is canonical; audio_excitement is retained only as its project alias.",
            "Level 1 and Level 2 are machine-assisted SILVER outcomes, not human-validated gold labels.",
            "AUTO_ADJUDICATED is machine-assisted SILVER, not human-validated gold.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
