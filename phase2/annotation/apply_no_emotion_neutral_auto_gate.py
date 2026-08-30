"""Apply a conservative machine gate for neutral speech with no emotion content.

This creates machine-adjudicated candidates. It never claims that a human
review occurred and never overwrites the original Phase 1 prediction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def text(row: pd.Series, *columns: str) -> str:
    for column in columns:
        if column in row.index:
            value = str(row[column]).strip()
            if value and value.lower() != "nan":
                return value
    return ""


def score(row: pd.Series, *columns: str) -> float:
    try:
        return float(text(row, *columns) or 0.0)
    except ValueError:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--target-threshold", type=float, default=0.90)
    parser.add_argument("--phase1-threshold", type=float, default=0.70)
    args = parser.parse_args()

    frame = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if "utterance_id" not in frame:
        raise SystemExit("Input manifest requires utterance_id")

    applied = []
    output = frame.copy()
    for column, default in {
        "machine_final_basic_emotion": "",
        "machine_final_basic_emotion_confidence": "",
        "machine_annotation_status": "UNRESOLVED",
        "auto_gate_critical_conflict": "YES",
        "auto_gate_reason": "",
        "auto_gate_human_review_required": "YES",
        "auto_gate_temporal_scope": "",
    }.items():
        if column not in output:
            output[column] = default

    for index, row in output.iterrows():
        target = text(row, "fused_target_scope", "auto_review_target_scope", "deberta_target_scope").upper()
        target_conf = score(row, "deberta_target_scope_confidence")
        phase1 = text(row, "phase1_basic_emotion", "phase1_candidate_emotion").lower()
        phase1_conf = score(row, "phase1_basic_emotion_confidence", "emotion_label_confidence")
        qualifies = (
            target == "NO_EMOTION_CONTENT"
            and target_conf >= args.target_threshold
            and phase1 == "neutral"
            and phase1_conf >= args.phase1_threshold
        )
        output.at[index, "auto_gate_temporal_scope"] = "NOT_APPLICABLE" if target == "NO_EMOTION_CONTENT" else text(row, "deberta_temporal_scope", "auto_review_temporal_scope")
        if qualifies:
            output.at[index, "machine_final_basic_emotion"] = "neutral"
            output.at[index, "machine_final_basic_emotion_confidence"] = f"{phase1_conf:.6f}"
            output.at[index, "machine_annotation_status"] = "AUTO_ADJUDICATED"
            output.at[index, "auto_gate_critical_conflict"] = "NO"
            output.at[index, "auto_gate_human_review_required"] = "NO"
            output.at[index, "auto_gate_reason"] = "NO_EMOTION_CONTENT high confidence plus Phase 1 neutral high confidence"
            applied.append(row["utterance_id"])

    destination = Path(args.output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(output),
        "auto_adjudicated_rows": len(applied),
        "unresolved_rows": int((output["machine_annotation_status"] == "UNRESOLVED").sum()),
        "target_threshold": args.target_threshold,
        "phase1_threshold": args.phase1_threshold,
        "notes": [
            "This is machine adjudication, not human review.",
            "The original Phase 1 emotion and DeBERTa fields are preserved.",
            "NO_EMOTION_CONTENT receives NOT_APPLICABLE temporal scope.",
            "No deception, credibility, truthfulness, or reliability label is inferred.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
