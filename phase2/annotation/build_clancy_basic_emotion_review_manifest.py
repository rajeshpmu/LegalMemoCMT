"""Build a complete Clancy basic-emotion reviewer copy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REVIEW_COLUMNS = {
    "human_basic_emotion": "",
    "human_basic_emotion_review_status": "UNREVIEWED",
    "human_basic_emotion_confidence": "",
    "human_basic_emotion_reviewer": "",
    "human_basic_emotion_notes": "",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-csv", required=True, help="Machine-promoted rows, preferred for provenance")
    parser.add_argument("--candidates-csv", required=True, help="Full candidate pool, including unresolved rows")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output = Path(args.output_csv)
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite existing reviewer file: {output}; use --overwrite only intentionally")

    machine = pd.read_csv(args.machine_csv, dtype=str).fillna("")
    candidates = pd.read_csv(args.candidates_csv, dtype=str).fillna("")
    for name, frame in (("machine", machine), ("candidates", candidates)):
        if "utterance_id" not in frame.columns:
            raise SystemExit(f"{name} CSV requires utterance_id")
        if frame["utterance_id"].duplicated().any():
            raise SystemExit(f"{name} CSV contains duplicate utterance_id values")

    # Start with every candidate so unresolved rows remain available for review.
    out = candidates.copy()
    machine_only = machine[~machine["utterance_id"].isin(out["utterance_id"])].copy()
    if not machine_only.empty:
        out = pd.concat([out, machine_only], ignore_index=True, sort=False)

    # Fill missing provenance columns from the promoted machine view without
    # replacing any newer values already present in the full candidate pool.
    machine_index = machine.set_index("utterance_id")
    for column in machine.columns:
        if column == "utterance_id":
            continue
        if column not in out.columns:
            out[column] = out["utterance_id"].map(machine_index[column]).fillna("")

    for column, default in REVIEW_COLUMNS.items():
        if column not in out.columns:
            out[column] = default

    out = out.drop_duplicates("utterance_id", keep="first")
    out = out.sort_values("utterance_id", kind="stable").reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)

    summary = {
        "machine_csv": args.machine_csv,
        "candidates_csv": args.candidates_csv,
        "output_csv": args.output_csv,
        "machine_rows": len(machine),
        "candidate_rows": len(candidates),
        "machine_rows_added": len(machine_only),
        "rows_written": len(out),
        "review_status_counts": out["human_basic_emotion_review_status"].value_counts(dropna=False).to_dict(),
        "notes": [
            "The reviewer copy contains promoted and unresolved training candidates.",
            "Human fields are initialized but no human emotion label is inferred.",
            "Use CONFIRMED, REJECTED, or DEFERRED after inspecting transcript, audio, and video.",
            "Only CONFIRMED human_basic_emotion values are treated as human gold by the merge stage.",
            "Machine provenance and predictions are preserved unchanged.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
