"""Propose courtroom-affect candidates from transcript, audio, and visual evidence.

This is an interpretable weak-label/review tool. It does not infer credibility,
truthfulness, deception, or a gold courtroom-affect label.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

WORD = re.IGNORECASE
HESITATION = re.compile(r"\b(um+|uh+|er+|well|perhaps|maybe|i think|i believe|not sure)\b", WORD)
QUALIFICATION = re.compile(r"\b(i (?:don't|do not|can't|cannot) recall|i am not sure|to the best of my knowledge|approximately|as far as i know|i believe|i think|perhaps|maybe)\b", WORD)
UNCERTAINTY = re.compile(r"\b(i (?:don't|do not) believe|i(?:'m| am) not sure|i (?:don't|do not) know|i (?:don't|do not) recall|maybe|perhaps|possibly|i think|i believe)\b", WORD)
DEFENSIVE = re.compile(r"\b(that(?:'s| is) not correct|i disagree|not true|i did not|i never|you are mistaken|misunderstood|correct that|no,?\s+i)\b", WORD)
ASSERTIVE = re.compile(r"\b(absolutely|definitely|certainly|of course|i know|i did|yes,?\s+i did|no,?\s+i did not)\b", WORD)
REPETITION = re.compile(r"\b(\w+)\s+\1\b", WORD)
INTERRUPTION = re.compile(r"--|…|\.\.\.|\bwait\b|\bsorry\b", WORD)


def clean(value: object) -> str:
    return str(value or "").strip()


def number(row: dict[str, str], key: str) -> float | None:
    try: return float(clean(row.get(key)))
    except (TypeError, ValueError): return None


def propose(row: dict[str, str]) -> dict[str, str]:
    text = clean(row.get("utterance_text")) or clean(row.get("turn_text"))
    # Prefer the project-facing alias while accepting legacy manifests.
    arousal = number(row, "audio_excitement") or number(row, "audio_arousal")
    valence = number(row, "audio_valence")
    dominance = number(row, "audio_dominance")
    speech = clean(row.get("audio_emotion_candidate")).lower()
    visible = clean(row.get("speaker_visible_during_speech")).upper() == "YES"
    visual_match = clean(row.get("visual_speaker_match")).upper() == "YES"
    hesitation = bool(HESITATION.search(text))
    qualification = bool(QUALIFICATION.search(text))
    defensive = bool(DEFENSIVE.search(text))
    assertive = bool(ASSERTIVE.search(text))
    repetition = bool(REPETITION.search(text))
    interruption = bool(INTERRUPTION.search(text))
    uncertainty = bool(UNCERTAINTY.search(text))
    non_speech = bool(re.search(r"\[(?:snorts?|sighs?|laughs?|cries?|coughs?|breathes?|inaudible)\]", text, re.IGNORECASE))
    scope = clean(row.get("emotion_target_scope")).upper()
    distress_categorical = speech in {"sad", "ang", "fear"}
    distress_language = bool(re.search(r"\b(crying|cried|tearful|panic|panicked|terrified|overwhelmed|desperate|hopeless|suicidal)\b", text, re.IGNORECASE))
    visual_distress = clean(row.get("visual_distress_evidence")).upper() == "YES"
    scores: dict[str, float] = {x: 0.0 for x in ["CALM_COMPOSED", "HESITANT_UNCERTAIN", "GUARDED", "DEFENSIVE", "ASSERTIVE", "TENSE", "DISTRESSED", "AGITATED"]}
    evidence: dict[str, list[str]] = {x: [] for x in scores}
    missing: dict[str, list[str]] = {x: [] for x in scores}

    if speech in {"neu", "neutral"}: scores["CALM_COMPOSED"] += .35; evidence["CALM_COMPOSED"].append("neutral SpeechBrain output")
    if arousal is not None and arousal < .45: scores["CALM_COMPOSED"] += .30; evidence["CALM_COMPOSED"].append("arousal<0.45")
    else: missing["CALM_COMPOSED"].append("low/moderate arousal")
    if visible and visual_match: scores["CALM_COMPOSED"] += .25; evidence["CALM_COMPOSED"].append("human visual speaker match")
    else: missing["CALM_COMPOSED"].append("stable visual behavior evidence")

    if hesitation: scores["HESITANT_UNCERTAIN"] += .25; evidence["HESITANT_UNCERTAIN"].append("hesitation marker")
    else: missing["HESITANT_UNCERTAIN"].append("hesitation marker")
    # Epistemic uncertainty is stronger evidence for hesitant/uncertain than
    # generic arousal is for tension, but remains a review candidate.
    if uncertainty: scores["HESITANT_UNCERTAIN"] += .35; evidence["HESITANT_UNCERTAIN"].append("epistemic uncertainty/qualification")
    else: missing["HESITANT_UNCERTAIN"].append("epistemic uncertainty/qualification")
    if dominance is not None and dominance < .55: scores["HESITANT_UNCERTAIN"] += .15; evidence["HESITANT_UNCERTAIN"].append("not-high dominance")
    else: missing["HESITANT_UNCERTAIN"].append("low/moderate dominance")

    if qualification: scores["GUARDED"] += .45; evidence["GUARDED"].append("qualification/refusal wording")
    else: missing["GUARDED"].append("qualification/refusal wording")
    if dominance is not None and dominance < .50: scores["GUARDED"] += .25; evidence["GUARDED"].append("dominance<0.50")
    else: missing["GUARDED"].append("low/moderate dominance")
    missing["GUARDED"].append("attorney-question interaction context")

    if defensive: scores["DEFENSIVE"] += .50; evidence["DEFENSIVE"].append("correction/disagreement wording")
    else: missing["DEFENSIVE"].append("correction/disagreement wording")
    if arousal is not None and arousal >= .45: scores["DEFENSIVE"] += .25; evidence["DEFENSIVE"].append("elevated arousal")
    else: missing["DEFENSIVE"].append("prosodic activation")
    missing["DEFENSIVE"].append("preceding challenge/contradiction context")

    if dominance is not None and dominance >= .50: scores["ASSERTIVE"] += .45; evidence["ASSERTIVE"].append("dominance>=0.50")
    else: missing["ASSERTIVE"].append("high dominance")
    if assertive: scores["ASSERTIVE"] += .35; evidence["ASSERTIVE"].append("firm direct-response wording")
    else: missing["ASSERTIVE"].append("firm direct-response wording")
    if arousal is not None and arousal >= .40: scores["ASSERTIVE"] += .15; evidence["ASSERTIVE"].append("moderate/elevated arousal")
    else: missing["ASSERTIVE"].append("stronger voice/prosody")

    if arousal is not None and arousal >= .45 and not (uncertainty and hesitation): scores["TENSE"] += .35; evidence["TENSE"].append("arousal>=0.45")
    elif uncertainty and hesitation: missing["TENSE"].append("uncertainty takes precedence over generic tension")
    else: missing["TENSE"].append("elevated arousal")
    if valence is not None and valence <= .45: scores["TENSE"] += .25; evidence["TENSE"].append("valence<=0.45")
    else: missing["TENSE"].append("negative valence")
    if hesitation: scores["TENSE"] += .20; evidence["TENSE"].append("hesitation markers")
    else: missing["TENSE"].append("hesitation/voice-tension evidence")

    if valence is not None and valence <= .30: scores["DISTRESSED"] += .35; evidence["DISTRESSED"].append("valence<=0.30")
    else: missing["DISTRESSED"].append("strong negative valence")
    if arousal is not None and arousal >= .45: scores["DISTRESSED"] += .30; evidence["DISTRESSED"].append("arousal>=0.45")
    else: missing["DISTRESSED"].append("elevated arousal")
    if distress_categorical: scores["DISTRESSED"] += .15; evidence["DISTRESSED"].append("negative categorical audio evidence")
    else: missing["DISTRESSED"].append("negative categorical audio evidence")
    if distress_language:
        scores["DISTRESSED"] += .20; evidence["DISTRESSED"].append("distress-specific linguistic cue")
    else: missing["DISTRESSED"].append("distress-specific linguistic cue")
    if visual_distress:
        scores["DISTRESSED"] += .20; evidence["DISTRESSED"].append("visual distress evidence")
    else: missing["DISTRESSED"].append("human-confirmed vocal/visual distress")

    if arousal is not None and arousal >= .50: scores["AGITATED"] += .35; evidence["AGITATED"].append("arousal>=0.50")
    else: missing["AGITATED"].append("high arousal")
    if valence is not None and valence <= .40: scores["AGITATED"] += .25; evidence["AGITATED"].append("valence<=0.40")
    else: missing["AGITATED"].append("negative valence")
    if repetition or interruption: scores["AGITATED"] += .20; evidence["AGITATED"].append("repetition/interruption marker")
    else: missing["AGITATED"].append("interruption/repetition/speech-rate change")

    # Candidate threshold is deliberately high for weak evidence. Ties are broken
    # by the order above, and every candidate remains human-review required.
    # V/A/D can indicate negative activation, but cannot by themselves identify
    # distress. Require at least one corroborating categorical, linguistic, or
    # visual cue before exposing DISTRESSED as a candidate class.
    distress_corroborated = distress_categorical or distress_language or visual_distress
    if not distress_corroborated:
        scores["DISTRESSED"] = 0.0
        evidence["DISTRESSED"] = []
    if uncertainty and hesitation:
        label, score = "HESITANT_UNCERTAIN", scores["HESITANT_UNCERTAIN"]
    else:
        label, score = max(scores.items(), key=lambda item: item[1])
    if score < .60:
        label, score = "UNKNOWN", 0.0
    phase1_confidence = number(row, "phase1_basic_emotion_confidence")
    basic_candidate = clean(row.get("phase1_basic_emotion")) or "UNKNOWN"
    basic_confidence = phase1_confidence if phase1_confidence is not None else 0.0
    basic_basis = "preserve Phase 1 candidate for human review"
    scope_supports_neutral = scope in {"OTHER_PERSON_DESCRIBED", "EVENT_DESCRIBED", "QUOTED_SPEECH"}
    if scope_supports_neutral and phase1_confidence is not None and phase1_confidence < .60 and basic_candidate != "neutral":
        basic_candidate, basic_confidence = "neutral", .75
        basic_basis = "low-confidence non-neutral Phase 1 output targets described/quoted content rather than a clearly self-expressed emotion"
    if non_speech:
        non_speech_note = "non-speech marker retained as context only; it is not mapped directly to emotion"
    else:
        non_speech_note = "no bracketed non-speech marker detected"
    if scope_supports_neutral:
        speaker_emotion_evidence = "NO"
    elif scope == "SELF_EXPRESSED":
        speaker_emotion_evidence = "YES"
    else:
        speaker_emotion_evidence = "UNKNOWN"
    if basic_candidate == "neutral" and clean(row.get("phase1_basic_emotion")).lower() == "disgust":
        review_reason = "PHASE1_DISGUST_NOT_SUPPORTED_BY_MULTIMODAL_REVIEW"
    elif uncertainty and hesitation:
        review_reason = "UNCERTAINTY_PRECEDES_GENERIC_TENSION"
    else:
        review_reason = "MACHINE_CANDIDATE_REQUIRES_HUMAN_REVIEW"
    return {
        "proposed_courtroom_affect": label,
        "proposed_courtroom_affect_confidence": f"{score:.2f}",
        "courtroom_affect_evidence": "; ".join(evidence.get(label, [])),
        "courtroom_affect_missing_evidence": "; ".join(missing.get(label, [])),
        "courtroom_affect_review_required": "YES",
        "courtroom_affect_rule_version": "scope_audio_visual_v3_clean_affect_taxonomy",
        "negative_activation_candidate": "YES" if (arousal is not None and arousal >= .45 and valence is not None and valence <= .45) else "NO",
        "distress_corroboration_present": "YES" if distress_corroborated else "NO",
        "speaker_emotion_evidence_present": speaker_emotion_evidence,
        "non_speech_marker_present": "YES" if non_speech else "NO",
        "non_speech_marker_interpretation": non_speech_note,
        "response_stance_candidate": "UNCERTAIN_RESPONSE" if uncertainty else "UNKNOWN",
        "basic_emotion_review_candidate": basic_candidate,
        "basic_emotion_review_candidate_confidence": f"{basic_confidence:.2f}",
        "basic_emotion_review_basis": basic_basis,
        "human_review_reason_candidate": review_reason,
        "proposed_affect_intensity": "UNKNOWN",
        **{f"courtroom_affect_score_{key.lower()}": f"{value:.2f}" for key, value in scores.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--max-rows", type=int, default=0)
    args = parser.parse_args()
    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle: rows = list(csv.DictReader(handle))
    if args.max_rows > 0: rows = rows[:args.max_rows]
    output=[]
    for row in rows:
        enriched=dict(row); enriched.update(propose(row)); output.append(enriched)
    out=Path(args.output_csv); out.parent.mkdir(parents=True,exist_ok=True)
    fields=list(output[0]) if output else []
    with out.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(output)
    summary={"input_csv":args.input_csv,"output_csv":args.output_csv,"rows_processed":len(output),"affect_counts":dict(Counter(r["proposed_courtroom_affect"] for r in output)),"review_required_counts":dict(Counter(r["courtroom_affect_review_required"] for r in output)),"notes":["All values are weak candidates requiring human review.","No credibility, truthfulness, deception, or reliability inference is made.","Missing interaction and speech-rate features are recorded rather than invented."]}
    report=Path(args.summary_json); report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__": main()
