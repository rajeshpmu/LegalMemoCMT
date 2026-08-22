from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common import ANNOTATION_STATUSES, BASIC_EMOTIONS, COURTROOM_AFFECT, ensure_annotation_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate annotation statuses and provenance")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--issues-csv", required=True)
    args = parser.parse_args()
    df = ensure_annotation_schema(pd.read_csv(args.input_csv, dtype=str).fillna(""))
    issues = []
    if "utterance_id" in df and df["utterance_id"].duplicated().any():
        issues.extend({"utterance_id": uid, "issue": "duplicate_utterance_id"} for uid in df.loc[df["utterance_id"].duplicated(), "utterance_id"])
    for status_col in ["basic_emotion_annotation_status", "courtroom_affect_annotation_status"]:
        for value in sorted(set(df[status_col])):
            if value not in ANNOTATION_STATUSES:
                issues.append({"utterance_id": "", "issue": f"invalid_{status_col}:{value}"})
    for _, row in df.iterrows():
        if row.get("basic_emotion", "") and row["basic_emotion"] not in BASIC_EMOTIONS:
            issues.append({"utterance_id": row.get("utterance_id", ""), "issue": "invalid_basic_emotion"})
        if row.get("courtroom_affect", "") and row["courtroom_affect"] not in COURTROOM_AFFECT:
            issues.append({"utterance_id": row.get("utterance_id", ""), "issue": "invalid_courtroom_affect"})
        if row.get("basic_emotion_annotation_status") in {"HUMAN_SINGLE", "HUMAN_MULTI", "ADJUDICATED"} and row.get("basic_emotion_source") != "manual_annotation":
            issues.append({"utterance_id": row.get("utterance_id", ""), "issue": "human_basic_label_missing_manual_source"})
        if row.get("courtroom_affect_annotation_status") in {"HUMAN_SINGLE", "HUMAN_MULTI", "ADJUDICATED"} and not row.get("courtroom_affect", ""):
            issues.append({"utterance_id": row.get("utterance_id", ""), "issue": "human_affect_status_without_label"})
    issue_df = pd.DataFrame(issues, columns=["utterance_id", "issue"])
    issue_path = Path(args.issues_csv)
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    issue_df.to_csv(issue_path, index=False)
    summary = {"rows": len(df), "unique_utterance_ids": int(df["utterance_id"].nunique()) if "utterance_id" in df else 0, "issues": len(issue_df), "status": "PASS" if issue_df.empty else "FAIL", "basic_emotion_status_counts": df["basic_emotion_annotation_status"].value_counts().to_dict(), "courtroom_affect_status_counts": df["courtroom_affect_annotation_status"].value_counts().to_dict(), "human_labels_are_not_replaced_by_suggestions": True}
    Path(args.summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
