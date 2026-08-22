from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import ANNOTATION_STATUSES, BASIC_EMOTIONS, COURTROOM_AFFECT, ensure_annotation_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge reviewed annotations without overwriting provenance")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--human-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--review-status", default="HUMAN_SINGLE", choices=sorted(ANNOTATION_STATUSES))
    args = parser.parse_args()
    base = ensure_annotation_schema(pd.read_csv(args.input_csv, dtype=str).fillna(""))
    human = pd.read_csv(args.human_csv, dtype=str).fillna("")
    if "utterance_id" not in base or "utterance_id" not in human:
        raise SystemExit("Both manifests require utterance_id")
    human = human.drop_duplicates("utterance_id").set_index("utterance_id")
    unknown = human.index[~human.index.isin(set(base["utterance_id"]))].tolist()[:5]
    if unknown:
        raise SystemExit(f"Human annotation contains unknown utterance IDs: {unknown}")
    for index, row in base.iterrows():
        uid = row["utterance_id"]
        if uid not in human.index:
            continue
        reviewed = human.loc[uid]
        if reviewed.get("basic_emotion", ""):
            if reviewed["basic_emotion"] not in BASIC_EMOTIONS:
                raise SystemExit(f"Invalid basic emotion for {uid}: {reviewed['basic_emotion']}")
            base.at[index, "basic_emotion"] = reviewed["basic_emotion"]
            base.at[index, "emotion_label"] = reviewed["basic_emotion"]
            base.at[index, "basic_emotion_source"] = "manual_annotation"
            base.at[index, "emotion_label_source"] = "manual_annotation"
            base.at[index, "basic_emotion_annotation_status"] = args.review_status
        if reviewed.get("courtroom_affect", ""):
            if reviewed["courtroom_affect"] not in COURTROOM_AFFECT:
                raise SystemExit(f"Invalid courtroom affect for {uid}: {reviewed['courtroom_affect']}")
            base.at[index, "courtroom_affect"] = reviewed["courtroom_affect"]
            base.at[index, "courtroom_affect_confidence"] = reviewed.get("courtroom_affect_confidence", "")
            base.at[index, "courtroom_affect_annotation_status"] = args.review_status
        for column in ["affect_intensity", "valence", "arousal", "response_stance", "annotation_context_start", "annotation_context_end", "annotation_notes"]:
            if column in reviewed and reviewed[column]:
                base.at[index, column] = reviewed[column]
        base.at[index, "review_timestamp"] = reviewed.get("review_timestamp", "")
        base.at[index, "label_changed_after_review"] = reviewed.get("label_changed_after_review", "")
    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(out, index=False)
    print(f"Merged reviewed annotations into {len(base)} rows at {out}")


if __name__ == "__main__":
    main()
