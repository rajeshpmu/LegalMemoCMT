"""Merge human-gold fields and create one common training label."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-csv", required=True)
    parser.add_argument("--human-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--human-label-column", default="human_basic_emotion")
    parser.add_argument("--human-status-column", default="human_basic_emotion_review_status")
    parser.add_argument("--confirmed-value", default="CONFIRMED")
    args = parser.parse_args()

    machine = pd.read_csv(args.machine_csv, dtype=str).fillna("")
    human = pd.read_csv(args.human_csv, dtype=str).fillna("")
    for name, frame in [("machine", machine), ("human", human)]:
        if "utterance_id" not in frame:
            raise SystemExit(f"{name} CSV requires utterance_id")
    if machine["utterance_id"].duplicated().any():
        raise SystemExit("Machine CSV contains duplicate utterance_id values")
    if human["utterance_id"].duplicated().any():
        raise SystemExit("Human CSV contains duplicate utterance_id values")

    human = human.set_index("utterance_id")
    out = machine.copy()
    matched = out["utterance_id"].isin(human.index)
    human_columns = [c for c in human.columns]
    human_label_output_column = args.human_label_column
    human_status_output_column = args.human_status_column
    for column in human_columns:
        target = column if column not in out.columns else f"{column}_human_source"
        values = out["utterance_id"].map(human[column]).fillna("")
        out[target] = values
        if column == args.human_label_column:
            human_label_output_column = target
        if column == args.human_status_column:
            human_status_output_column = target

    label = pd.Series("", index=out.index)
    source = pd.Series("", index=out.index)
    status = pd.Series("UNRESOLVED", index=out.index)

    human_label = out.get(human_label_output_column, pd.Series("", index=out.index))
    human_status = out.get(human_status_output_column, pd.Series("", index=out.index))
    confirmed = human_status.str.upper().eq(args.confirmed_value.upper()) & human_label.ne("")
    label.loc[confirmed] = human_label.loc[confirmed]
    source.loc[confirmed] = "HUMAN_GOLD"
    status.loc[confirmed] = "HUMAN_CONFIRMED"

    remaining = ~confirmed
    machine_label = out.get("final_training_basic_emotion", pd.Series("", index=out.index))
    machine_status = out.get("final_training_label_status", pd.Series("", index=out.index))
    machine_ok = remaining & machine_label.ne("") & machine_label.ne("UNRESOLVED")
    label.loc[machine_ok] = machine_label.loc[machine_ok]
    source.loc[machine_ok] = machine_status.loc[machine_ok].replace("", "MACHINE")
    status.loc[machine_ok] = "MACHINE_ASSISTED"

    out["training_label"] = label
    out["training_label_source"] = source
    out["training_label_status"] = status
    out["training_label_is_human_gold"] = out["training_label_source"].eq("HUMAN_GOLD").map({True: "YES", False: "NO"})
    out["training_label_review_required"] = out["training_label_source"].ne("HUMAN_GOLD").map({True: "YES", False: "NO"})
    out = out[out["training_label"].ne("")].copy()

    destination = Path(args.output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(destination, index=False)
    summary = {
        "machine_csv": args.machine_csv,
        "human_csv": args.human_csv,
        "output_csv": args.output_csv,
        "machine_rows": len(machine),
        "human_rows": len(human),
        "matched_machine_rows": int(matched.sum()),
        "rows_written": len(out),
        "training_label_counts": out["training_label"].value_counts().to_dict(),
        "training_label_source_counts": out["training_label_source"].value_counts().to_dict(),
        "notes": [
            "training_label is the common target field for training/fine-tuning.",
            "Confirmed human labels take priority over machine labels.",
            "Machine labels remain explicitly marked MACHINE_ASSISTED.",
            "Human and machine source fields are preserved separately.",
            "Use a human-confirmed test manifest for final evaluation.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
