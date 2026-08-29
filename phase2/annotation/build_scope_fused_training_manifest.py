"""Build a provenance-preserving scope-fused Clancy training manifest.

Semantic scope comes from the suggestion/DeBERTa layer. Audio, video, and
diarization are used only to assess whether the current speaker has usable
speaker-emotion evidence and whether the row is safe for weak-label training.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def value(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row.index:
            text = str(row[name]).strip()
            if text and text.lower() != "nan":
                return text
    return ""


def yes(row: pd.Series, *names: str) -> bool:
    return value(row, *names).upper() in {"YES", "TRUE", "1", "VALID"}


def confidence(row: pd.Series) -> float:
    try:
        return float(value(row, "auto_review_confidence_score", "deberta_target_scope_confidence") or 0)
    except ValueError:
        return 0.0


def build_row(row: pd.Series, basic_threshold: float) -> dict[str, str]:
    target = value(row, "human_target_scope", "auto_review_target_scope", "deberta_target_scope") or "UNCLEAR"
    temporal = value(row, "human_temporal_scope", "auto_review_temporal_scope", "deberta_temporal_scope") or "UNCLEAR"
    human_status = value(row, "human_scope_review_status").upper()
    original = value(row, "emotion_target_scope") or "UNCLEAR"
    deberta = value(row, "deberta_target_scope") or "UNCLEAR"
    target_disagreement = value(row, "target_scope_disagreement").upper() == "YES"
    low_margin = False
    for field in ("deberta_target_margin", "deberta_temporal_margin"):
        try:
            if value(row, field) and float(value(row, field)) < 0.10:
                low_margin = True
        except ValueError:
            low_margin = True

    role = value(row, "speaker_role").lower()
    speaking = value(row, "witness_speaking_status").upper()
    witness_speaking = role == "witness" and speaking == "SPEAKING"
    audio_valid = yes(row, "audio_present") and value(row, "audio_validation_status").lower() in {"valid", "ok", "pass"}
    visual_valid = yes(row, "visual_speaker_match") and yes(row, "speaker_visible_during_speech")
    diarization_present = bool(value(row, "speaker_cluster_id"))
    critical_reasons = []
    if target_disagreement:
        critical_reasons.append("target_scope_disagreement")
    if confidence(row) < basic_threshold:
        critical_reasons.append("low_semantic_confidence")
    if low_margin:
        critical_reasons.append("low_scope_margin")
    if role and role != "witness":
        critical_reasons.append("non_witness_speaker")
    if speaking and speaking not in {"SPEAKING", "YES"}:
        critical_reasons.append("witness_not_speaking")
    if value(row, "visual_speaker_match") and not visual_valid:
        critical_reasons.append("visual_speaker_not_confirmed")
    if value(row, "audio_validation_status") and not audio_valid:
        critical_reasons.append("audio_not_valid")

    if human_status == "CONFIRMED" and value(row, "human_target_scope"):
        status = "HUMAN_VALIDATED"
        tier = "GOLD_REVIEWED"
        final_target = value(row, "human_target_scope")
        final_temporal = value(row, "human_temporal_scope") or "UNCLEAR"
    elif not critical_reasons and value(row, "auto_review_target_scope") and confidence(row) >= basic_threshold:
        status = "SILVER_CANDIDATE"
        tier = "SILVER_WEAK_LABEL"
        final_target = target
        final_temporal = temporal
    else:
        status = "UNRESOLVED"
        tier = "WEAK"
        final_target = ""
        final_temporal = ""

    if target == "NO_EMOTION_CONTENT":
        speaker_evidence = "NO" if value(row, "speaker_emotion_evidence_present").upper() == "NO" else "UNKNOWN"
    elif witness_speaking and (audio_valid or visual_valid):
        speaker_evidence = "YES"
    else:
        speaker_evidence = "UNKNOWN"

    training_eligible = "YES" if status in {"HUMAN_VALIDATED", "SILVER_CANDIDATE"} else "NO"
    out = row.to_dict()
    out.update({
        "fused_target_scope": target,
        "fused_temporal_scope": temporal,
        "final_emotion_target_scope": final_target,
        "final_emotion_temporal_scope": final_temporal,
        "speaker_emotion_evidence_present_fused": speaker_evidence,
        "audio_evidence_for_speaker": "YES" if audio_valid else "NO",
        "visual_evidence_for_speaker": "YES" if visual_valid else "NO",
        "diarization_evidence_present": "YES" if diarization_present else "NO",
        "scope_fusion_status": status,
        "scope_fusion_tier": tier,
        "scope_training_eligible": training_eligible,
        "scope_fusion_critical_conflict": "YES" if critical_reasons else "NO",
        "scope_fusion_reason": "; ".join(critical_reasons) or "semantic suggestion supported by configured evidence checks",
        "scope_fusion_rule_version": "semantic_first_audio_video_validation_v1",
    })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True, help="Output of suggest_human_scope_annotation.py")
    parser.add_argument("--output-csv", required=True, help="Complete additive fusion manifest")
    parser.add_argument("--eligible-csv", required=True, help="Filtered rows eligible for weak-label training")
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--basic-threshold", type=float, default=0.60)
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if "utterance_id" not in frame:
        raise SystemExit("Input manifest requires utterance_id")
    if frame["utterance_id"].duplicated().any():
        raise SystemExit("Input manifest contains duplicate utterance_id values")
    rows = [build_row(row, args.basic_threshold) for _, row in frame.iterrows()]
    output = pd.DataFrame(rows)
    eligible = output[output["scope_training_eligible"] == "YES"].copy()
    for path, data in ((args.output_csv, output), (args.eligible_csv, eligible)):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(destination, index=False)
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "eligible_csv": args.eligible_csv,
        "rows_processed": len(output),
        "training_eligible_rows": len(eligible),
        "scope_fusion_status_counts": output["scope_fusion_status"].value_counts().to_dict(),
        "scope_fusion_tier_counts": output["scope_fusion_tier"].value_counts().to_dict(),
        "final_target_counts": output.loc[output["final_emotion_target_scope"].ne(""), "final_emotion_target_scope"].value_counts().to_dict(),
        "critical_conflict_count": int((output["scope_fusion_critical_conflict"] == "YES").sum()),
        "speaker_emotion_evidence_counts": output["speaker_emotion_evidence_present_fused"].value_counts().to_dict(),
        "notes": [
            "Semantic target scope is derived from the suggestion/DeBERTa layer.",
            "Audio, video, and diarization validate speaker evidence and eligibility; they do not determine semantic target scope.",
            "SILVER_WEAK_LABEL rows are machine-assisted candidates, not human gold labels.",
            "Original, DeBERTa, audio, visual, and diarization fields are preserved unchanged.",
            "No deception, credibility, truthfulness, or reliability label is inferred.",
        ],
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
