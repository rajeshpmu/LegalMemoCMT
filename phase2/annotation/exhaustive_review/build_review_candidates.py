"""Build detailed AI-assisted review candidates without creating human labels."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from textwrap import shorten

import pandas as pd


BASIC = {"neutral", "anger", "disgust", "fear", "joy", "sadness", "surprise"}
CALIBRATION = {
    "lOcZ_IJbM3I_turn08614": ("neutral", "ASSERTIVE", "PHASE1_ANGER_FALSE_POSITIVE"),
    "DiurriBQxVs_turn00298": ("neutral", "CALM_COMPOSED", "CALM_CORRECTION_VS_ANGER"),
    "DiurriBQxVs_turn00281": ("neutral", "CALM_COMPOSED", "PHASE1_ANGER_FALSE_POSITIVE"),
}


def val(row: pd.Series, key: str) -> str:
    return str(row.get(key, "") or "").strip()


def num(row: pd.Series, key: str) -> float | None:
    try:
        return float(val(row, key))
    except ValueError:
        return None


def assess(row: pd.Series) -> dict[str, str]:
    utterance_id = val(row, "utterance_id")
    phase1 = val(row, "phase1_basic_emotion").lower()
    phase1_conf = num(row, "phase1_basic_emotion_confidence")
    speech = val(row, "audio_emotion_candidate").lower()
    speech_conf = num(row, "audio_emotion_confidence")
    target = val(row, "auto_review_target_scope") or val(row, "deberta_target_scope") or val(row, "emotion_target_scope")
    target_conf = num(row, "auto_review_confidence") or num(row, "deberta_target_scope_confidence") or 0.0
    arousal = num(row, "audio_arousal")
    if arousal is None:
        arousal = num(row, "audio_excitement")
    text = val(row, "utterance_text") or val(row, "turn_text")

    if utterance_id in CALIBRATION:
        basic, affect, pattern = CALIBRATION[utterance_id]
        rationale = "Calibration recommendation supplied from prior human multimodal review; requires explicit acceptance."
    elif target == "NO_EMOTION_CONTENT" and target_conf >= 0.80:
        basic, affect, pattern = "neutral", "UNCLEAR", "NONE"
        rationale = "High-confidence no-emotion semantic scope; the factual transcript does not provide a target emotion for the witness."
    elif speech in {"neu", "neutral"} and speech_conf is not None and speech_conf >= 0.80 and arousal is not None and arousal < 0.45:
        basic, affect, pattern = "neutral", "UNCLEAR", "NONE"
        rationale = "Neutral categorical audio evidence and low/moderate activation support a neutral candidate."
    elif phase1 in BASIC:
        basic, affect, pattern = phase1, val(row, "proposed_courtroom_affect") or "UNCLEAR", "NONE"
        rationale = "Phase 1 candidate retained because available automatic evidence does not justify a deterministic override."
    else:
        basic, affect, pattern = "", "UNCLEAR", "OTHER"
        rationale = "Insufficient evidence for an automatic basic-emotion recommendation."

    phase1_conf_text = f"{phase1_conf:.6f}" if phase1_conf is not None else ""
    confidence = "0.85" if utterance_id in CALIBRATION else "0.70" if basic else ""
    disagreement = val(row, "modality_disagreement_score") or "UNKNOWN"
    priority = "HIGH" if val(row, "critical_conflict").upper() == "YES" or disagreement == "HIGH" else "MEDIUM" if disagreement == "MEDIUM" else "LOW"
    visual_status = "OBSERVED_FROM_EXISTING_VERIFICATION" if val(row, "visual_verification_status").upper() in {"HUMAN_VERIFIED", "HUMAN_SINGLE"} else "INSUFFICIENT"
    audio_status = "AVAILABLE_NOT_DIRECTLY_INSPECTED"
    if utterance_id not in CALIBRATION and visual_status == "INSUFFICIENT":
        affect = "UNCLEAR"
    cues = []
    if re.search(r"\b(um+|uh+|er+|maybe|perhaps|i think|i believe|not sure)\b", text, re.I):
        cues.append("possible hesitation/qualification marker")
    if re.search(r"\b(that is correct|that's correct|like i said|i did|absolutely)\b", text, re.I):
        cues.append("possible emphatic or corrective wording")
    if not cues:
        cues.append("no deterministic transcript cue")

    return {
        "recommended_basic_emotion": basic,
        "recommended_basic_emotion_confidence": confidence,
        "recommended_courtroom_affect": affect,
        "recommended_courtroom_affect_confidence": "0.75" if affect not in {"", "UNCLEAR"} else "",
        "recommended_affect_intensity": "1" if affect not in {"", "UNCLEAR"} else "UNKNOWN",
        "recommended_target_scope": target or "UNCLEAR",
        "recommended_temporal_scope": val(row, "auto_review_temporal_scope") or val(row, "deberta_temporal_scope") or "UNCLEAR",
        "audio_review_status": audio_status,
        "visual_review_status": visual_status,
        "observable_cues": "; ".join(cues),
        "domain_adaptation_pattern": pattern,
        "modality_disagreement": disagreement,
        "critical_conflict": val(row, "critical_conflict") or ("YES" if phase1 and basic and phase1 != basic else "NO"),
        "annotation_priority": priority,
        "review_reason": rationale,
        "active_learning_significance": "Useful calibration/domain-adaptation case" if pattern != "NONE" else "Routine candidate requiring confirmation",
        "review_provenance": "AI_ASSISTED_REVIEW",
        "review_status": "READY_FOR_HUMAN_ACCEPTANCE",
        "human_decision": "",
        "human_reviewer": "",
        "human_review_timestamp": "",
        "phase1_snapshot": f"{phase1} @ {phase1_conf_text}",
    }


def markdown(row: pd.Series, candidate: dict[str, str]) -> str:
    fields = [
        ("Utterance ID", val(row, "utterance_id")),
        ("Source", val(row, "youtube_id")),
        ("Split", val(row, "split")),
        ("Speaker role", val(row, "speaker_role")),
        ("Start", val(row, "start_time") or val(row, "turn_start_time")),
        ("End", val(row, "end_time") or val(row, "turn_end_time")),
        ("Duration", val(row, "clip_duration_seconds")),
        ("Transcript", val(row, "utterance_text") or val(row, "turn_text")),
        ("Phase 1", f"{val(row, 'phase1_basic_emotion')} @ {val(row, 'phase1_basic_emotion_confidence')}"),
        ("SpeechBrain", f"{val(row, 'audio_emotion_candidate')} @ {val(row, 'audio_emotion_confidence')}"),
        ("Odyssey V/A/D", f"{val(row, 'audio_valence')} / {val(row, 'audio_arousal') or val(row, 'audio_excitement')} / {val(row, 'audio_dominance')}"),
        ("DeBERTa target", f"{val(row, 'deberta_target_scope')} @ {val(row, 'deberta_target_scope_confidence')}"),
        ("DeBERTa temporal", val(row, "deberta_temporal_scope")),
        ("Video clip", val(row, "clip_video_path")),
        ("Audio clip", val(row, "clip_audio_path")),
    ]
    lines = [f"# Human Review Candidate - {val(row, 'utterance_id')}", "", "## Source Information", ""]
    lines.extend(f"- **{key}:** {value or '[blank]'}" for key, value in fields)
    lines += ["", "## Audiovisual Observations", "", f"- **Audio review status:** {candidate['audio_review_status']}", f"- **Video review status:** {candidate['visual_review_status']}", "- Do not claim visual behavior was observed unless a reviewer actually inspected the clip.", "", "## Semantic Interpretation", "", f"- Target scope candidate: `{candidate['recommended_target_scope']}`", f"- Temporal scope candidate: `{candidate['recommended_temporal_scope']}`", "- Semantic content must not be confused with the current witness's expressed emotion.", "", "## Integrated Candidate", "", f"- **Basic emotion:** `{candidate['recommended_basic_emotion'] or 'UNRESOLVED'}` ({candidate['recommended_basic_emotion_confidence'] or 'N/A'})", f"- **Courtroom affect:** `{candidate['recommended_courtroom_affect']}` ({candidate['recommended_courtroom_affect_confidence'] or 'N/A'})", f"- **Affect intensity:** `{candidate['recommended_affect_intensity']}`", f"- **Observable cue candidates:** {candidate['observable_cues']}", f"- **Modality disagreement:** `{candidate['modality_disagreement']}`", f"- **Critical conflict:** `{candidate['critical_conflict']}`", f"- **Priority:** `{candidate['annotation_priority']}`", f"- **Domain pattern:** `{candidate['domain_adaptation_pattern']}`", "", "## Review Rationale", "", candidate["review_reason"], "", "## Active-Learning Significance", "", candidate["active_learning_significance"], "", "## Final Record Status", "", "```yaml", f"review_provenance: {candidate['review_provenance']}", f"review_status: {candidate['review_status']}", "human_decision: null", "annotation_status: AI_REVIEW_CANDIDATE", "human_review_status: UNREVIEWED", "```", "", "The record is not human-reviewed until an explicit promotion command is executed."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--reviews-dir", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--utterance-id", action="append", default=[], help="Process only these IDs; repeat as needed.")
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if "utterance_id" not in frame or frame["utterance_id"].duplicated().any():
        raise SystemExit("Input must contain unique utterance_id values")
    if args.utterance_id:
        wanted = set(args.utterance_id)
        frame = frame[frame["utterance_id"].isin(wanted)].copy()
        missing_ids = sorted(wanted - set(frame["utterance_id"]))
        if missing_ids:
            raise SystemExit(f"Requested utterance IDs were not found: {missing_ids}")
    elif args.max_rows > 0:
        frame = frame.head(args.max_rows).copy()

    review_rows = []
    reviews_dir = Path(args.reviews_dir); reviews_dir.mkdir(parents=True, exist_ok=True)
    for _, row in frame.iterrows():
        candidate = assess(row)
        output = dict(row)
        output.update(candidate)
        review_rows.append(output)
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", val(row, "utterance_id"))
        (reviews_dir / f"{safe_id}.md").write_text(markdown(row, candidate), encoding="utf-8")

    output_path = Path(args.output_csv); output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(review_rows).to_csv(output_path, index=False)
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "reviews_dir": args.reviews_dir,
        "rows_processed": len(review_rows),
        "review_status": "READY_FOR_HUMAN_ACCEPTANCE",
        "priority_counts": pd.DataFrame(review_rows)["annotation_priority"].value_counts().to_dict() if review_rows else {},
        "calibration_examples_in_batch": [x for x in CALIBRATION if x in set(frame["utterance_id"])],
        "notes": [
            "This stage creates AI-assisted candidates only; it does not create human labels.",
            "Audio and video are not claimed to be directly inspected by this script.",
            "Reviewers must inspect actual MP4/WAV media before promotion.",
            "No deception, truthfulness, credibility, or reliability label is inferred.",
        ],
    }
    report = Path(args.summary_json); report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
