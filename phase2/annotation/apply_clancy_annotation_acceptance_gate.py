"""Apply a conservative automatic acceptance gate to affect candidates.

This stage never overwrites machine candidates. It creates final_* fields for
machine-assisted dataset preparation and keeps critical conflicts unresolved.
It does not create gold labels or infer credibility, truthfulness, or deception.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def clean(value: object) -> str:
    return str(value or "").strip()


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(clean(row.get(key)))
    except (TypeError, ValueError):
        return 0.0


def assess(row: dict[str, str], basic_threshold: float, affect_threshold: float) -> dict[str, str]:
    basic = clean(row.get("basic_emotion_review_candidate")) or "UNRESOLVED"
    affect = clean(row.get("proposed_courtroom_affect")) or "UNKNOWN"
    basic_conf = number(row, "basic_emotion_review_candidate_confidence")
    affect_conf = number(row, "proposed_courtroom_affect_confidence")
    phase1 = clean(row.get("phase1_basic_emotion")).lower()
    scope = clean(row.get("emotion_target_scope")).upper()
    speaker_evidence = clean(row.get("speaker_emotion_evidence_present")).upper()
    distress_support = clean(row.get("distress_corroboration_present")).upper()
    negative_activation = clean(row.get("negative_activation_candidate")).upper()

    reasons: list[str] = []
    if basic_conf < basic_threshold:
        reasons.append("basic confidence below threshold")
    if affect_conf < affect_threshold:
        reasons.append("courtroom-affect confidence below threshold")
    if basic in {"", "UNKNOWN", "UNRESOLVED"}:
        reasons.append("basic emotion candidate unresolved")
    if affect in {"", "UNKNOWN", "UNRESOLVED"}:
        reasons.append("courtroom-affect candidate unresolved")

    # Narrow domain rule: when the original non-neutral prediction is weak,
    # there is no evidence of the speaker's own emotion or negative activation,
    # and the observed courtroom presentation is strongly calm/composed, accept
    # neutral as a SILVER basic-emotion candidate. The Phase 1 prediction stays
    # in phase1_basic_emotion for provenance.
    neutral_calm_override = (
        phase1 not in {"", "neutral"}
        and number(row, "phase1_basic_emotion_confidence") < 0.60
        and negative_activation == "NO"
        and distress_support == "NO"
        and speaker_evidence == "NO"
        and affect == "CALM_COMPOSED"
        and affect_conf >= 0.80
    )
    if neutral_calm_override:
        reasons = []

    # A non-neutral Phase 1 class changing to neutral is acceptable when the
    # transcript explicitly reports/quotes another person's emotion and the
    # behavioral candidate is calm. The same change is critical when the
    # presentation is hesitant/defensive/tensed, because the speaker's state
    # remains materially ambiguous.
    phase1_conflict = phase1 not in {"", "neutral"} and basic == "neutral"
    scope_protects_neutral = scope in {"OTHER_PERSON_DESCRIBED", "EVENT_DESCRIBED", "QUOTED_SPEECH"} and speaker_evidence == "NO"
    behavioral_ambiguity = affect in {"HESITANT_UNCERTAIN", "TENSE", "DEFENSIVE", "DISTRESSED", "AGITATED"}
    critical_conflict = phase1_conflict and not (scope_protects_neutral and affect == "CALM_COMPOSED")
    if critical_conflict:
        reasons.append("Phase 1/basic-emotion disagreement with unresolved speaker behavioral state")
    if affect == "DISTRESSED" and distress_support != "YES":
        critical_conflict = True
        reasons.append("DISTRESSED lacks corroboration")
    if behavioral_ambiguity and phase1_conflict and not scope_protects_neutral:
        critical_conflict = True
    if neutral_calm_override:
        # The explicit override is itself the documented adjudication rule for
        # this narrow evidence pattern; do not let the generic Phase 1-versus-
        # candidate check reclassify it as a conflict.
        critical_conflict = False
    if critical_conflict:
        reasons.append("critical conflict")

    accepted = neutral_calm_override or not reasons
    if accepted:
        status, tier = "AUTO_ADJUDICATED", "SILVER"
        final_basic, final_affect = "neutral" if neutral_calm_override else basic, affect
        review = "NO"
        reason = (
            "narrow neutral-calm override: weak non-neutral Phase 1 output, no negative activation, "
            "no distress corroboration, no speaker-emotion evidence, and CALM_COMPOSED>=0.80"
            if neutral_calm_override else "thresholds passed and no critical conflict"
        )
    else:
        status, tier = "UNRESOLVED", "WEAK"
        final_basic = "UNRESOLVED"
        final_affect = affect if affect not in {"", "UNKNOWN"} and affect_conf >= affect_threshold else "UNRESOLVED"
        review = "YES"
        reason = "; ".join(dict.fromkeys(reasons))

    return {
        "critical_conflict": "YES" if critical_conflict else "NO",
        "annotation_status": status,
        "annotation_tier": tier,
        "final_basic_emotion": final_basic,
        "final_courtroom_affect": final_affect,
        "final_basic_emotion_confidence": f"{basic_conf:.2f}" if accepted else "",
        "final_courtroom_affect_confidence": f"{affect_conf:.2f}" if accepted else (f"{affect_conf:.2f}" if final_affect != "UNRESOLVED" else ""),
        "human_review_required": review,
        "acceptance_gate_reason": reason,
        "acceptance_gate_rule_applied": "NEUTRAL_CALM_OVERRIDE_V1" if neutral_calm_override else "STANDARD_THRESHOLD_GATE_V1",
        "acceptance_gate_rule_version": "basic_0.70_affect_0.60_conflict_v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--basic-threshold", type=float, default=0.70)
    parser.add_argument("--affect-threshold", type=float, default=0.60)
    parser.add_argument("--max-rows", type=int, default=0)
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if args.max_rows > 0:
        rows = rows[:args.max_rows]

    output = []
    for row in rows:
        enriched = dict(row)
        enriched.update(assess(row, args.basic_threshold, args.affect_threshold))
        output.append(enriched)

    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output[0]) if output else []
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)

    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(output),
        "basic_threshold": args.basic_threshold,
        "affect_threshold": args.affect_threshold,
        "annotation_status_counts": dict(Counter(row["annotation_status"] for row in output)),
        "annotation_tier_counts": dict(Counter(row["annotation_tier"] for row in output)),
        "critical_conflict_counts": dict(Counter(row["critical_conflict"] for row in output)),
        "notes": [
            "AUTO_ADJUDICATED/SILVER is a machine-assisted acceptance tier, not a human gold label.",
            "Phase 1 predictions and heuristic candidates are preserved unchanged.",
            "UNRESOLVED/WEAK rows require human review before supervised training.",
            "No deception, credibility, truthfulness, or reliability inference is made.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
