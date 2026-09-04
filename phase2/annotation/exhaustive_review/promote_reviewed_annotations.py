"""Explicitly accept, modify, or reject one AI review candidate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


BASIC = {"neutral", "anger", "disgust", "fear", "joy", "sadness", "surprise"}
AFFECT = {"CALM_COMPOSED", "HESITANT_UNCERTAIN", "GUARDED", "DEFENSIVE", "ASSERTIVE", "TENSE", "DISTRESSED", "AGITATED", "UNCLEAR"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--utterance-id", required=True)
    parser.add_argument("--decision", choices=["accept", "modify", "reject"], required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--basic-emotion", default="")
    parser.add_argument("--courtroom-affect", default="")
    parser.add_argument("--basic-confidence", default="")
    parser.add_argument("--affect-confidence", default="")
    parser.add_argument("--affect-intensity", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, dtype=str).fillna("")
    matches = frame["utterance_id"].eq(args.utterance_id)
    if int(matches.sum()) != 1:
        raise SystemExit(f"Expected exactly one row for {args.utterance_id}; found {int(matches.sum())}")
    index = frame.index[matches][0]
    row = frame.loc[index]
    now = datetime.now(timezone.utc).isoformat()
    frame.at[index, "previous_recommended_basic_emotion"] = row.get("recommended_basic_emotion", "")
    frame.at[index, "previous_recommended_courtroom_affect"] = row.get("recommended_courtroom_affect", "")
    frame.at[index, "human_reviewer"] = args.reviewer
    frame.at[index, "human_review_timestamp"] = now
    frame.at[index, "human_decision"] = {"accept": "ACCEPTED", "modify": "MODIFIED", "reject": "REJECTED"}[args.decision]

    if args.decision in {"accept", "modify"}:
        basic = args.basic_emotion.strip().lower() if args.decision == "modify" and args.basic_emotion else str(row.get("recommended_basic_emotion", "")).strip().lower()
        affect = args.courtroom_affect.strip().upper() if args.decision == "modify" and args.courtroom_affect else str(row.get("recommended_courtroom_affect", "")).strip().upper()
        if basic not in BASIC:
            raise SystemExit(f"Accepted basic emotion must be one of {sorted(BASIC)}")
        if affect not in AFFECT:
            raise SystemExit(f"Accepted courtroom affect must be one of {sorted(AFFECT)}")
        frame.at[index, "human_basic_emotion"] = basic
        frame.at[index, "human_basic_emotion_confidence"] = args.basic_confidence or row.get("recommended_basic_emotion_confidence", "")
        frame.at[index, "human_courtroom_affect"] = affect
        frame.at[index, "human_courtroom_affect_confidence"] = args.affect_confidence or row.get("recommended_courtroom_affect_confidence", "")
        frame.at[index, "human_affect_intensity"] = args.affect_intensity or row.get("recommended_affect_intensity", "UNKNOWN")
        frame.at[index, "human_basic_emotion_review_status"] = "CONFIRMED"
        frame.at[index, "human_review_status"] = "REVIEWED"
        frame.at[index, "annotation_status"] = "HUMAN_SINGLE"
        frame.at[index, "review_status"] = "REVIEWED"
    else:
        frame.at[index, "human_basic_emotion_review_status"] = "REJECTED"
        frame.at[index, "human_review_status"] = "NEEDS_REASSESSMENT"
        frame.at[index, "annotation_status"] = "REJECTED"
        frame.at[index, "review_status"] = "NEEDS_REASSESSMENT"
    frame.at[index, "human_review_notes"] = args.notes
    frame.at[index, "review_provenance"] = "HUMAN_SINGLE"

    output = Path(args.output_csv); output.parent.mkdir(parents=True, exist_ok=True); frame.to_csv(output, index=False)
    print(f"{args.decision.upper()} applied to {args.utterance_id}; wrote {len(frame)} rows to {output}")


if __name__ == "__main__":
    main()
