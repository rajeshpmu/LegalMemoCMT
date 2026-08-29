"""Add confirmed human scope annotations without replacing machine evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


TARGETS = {
    "SELF_EXPRESSED",
    "OTHER_PERSON_DESCRIBED",
    "QUOTED_SPEECH",
    "EVENT_DESCRIBED",
    "NO_EMOTION_CONTENT",
    "MIXED",
    "UNCLEAR",
}
TEMPORAL = {"CURRENT", "PAST_SELF", "PAST_OTHER", "HYPOTHETICAL", "UNCLEAR"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True, help="Comparison or suggestion manifest")
    parser.add_argument("--human-csv", required=True, help="Reviewer-edited CSV")
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    base = pd.read_csv(args.input_csv, dtype=str).fillna("")
    human = pd.read_csv(args.human_csv, dtype=str).fillna("")
    required = {"utterance_id", "reviewed_target_scope", "reviewed_temporal_scope", "reviewer_decision"}
    missing = required - set(human.columns)
    if missing:
        raise SystemExit(f"Human CSV is missing columns: {sorted(missing)}")
    if base["utterance_id"].duplicated().any():
        raise SystemExit("Input manifest contains duplicate utterance_id values")
    human = human.drop_duplicates("utterance_id").set_index("utterance_id")
    unknown = sorted(set(human.index) - set(base["utterance_id"]))
    if unknown:
        raise SystemExit(f"Human CSV contains unknown utterance IDs: {unknown[:5]}")

    for column, allowed in (("reviewed_target_scope", TARGETS), ("reviewed_temporal_scope", TEMPORAL)):
        invalid = sorted({value for value in human[column] if value and value not in allowed})
        if invalid:
            raise SystemExit(f"Invalid {column} values: {invalid}")

    for column, default in {
        "human_scope_review_status": "UNREVIEWED",
        "human_target_scope": "",
        "human_temporal_scope": "",
        "human_scope_reviewer": "",
        "human_scope_review_notes": "",
    }.items():
        if column not in base:
            base[column] = default

    applied = 0
    for index, row in base.iterrows():
        uid = row["utterance_id"]
        if uid not in human.index:
            continue
        review = human.loc[uid]
        decision = str(review["reviewer_decision"]).strip().upper()
        if decision not in {"CONFIRMED", "REJECTED", "DEFERRED"}:
            raise SystemExit(f"Invalid reviewer_decision for {uid}: {decision}")
        base.at[index, "human_scope_review_status"] = decision
        base.at[index, "human_scope_reviewer"] = review.get("reviewer", "")
        base.at[index, "human_scope_review_notes"] = review.get("reviewer_notes", "")
        if decision == "CONFIRMED":
            base.at[index, "human_target_scope"] = review["reviewed_target_scope"]
            base.at[index, "human_temporal_scope"] = review["reviewed_temporal_scope"]
            applied += 1

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(output, index=False)
    print(f"Wrote {len(base)} rows; applied {applied} confirmed human scope annotations to {output}")


if __name__ == "__main__":
    main()
