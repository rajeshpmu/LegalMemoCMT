"""Create a provenance-preserving machine-promoted training-label manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--promote-level1-as-provisional-class", action="store_true")
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    required = {"utterance_id", "recovery_decision", "phase1_basic_emotion"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Input is missing columns: {', '.join(missing)}")

    out = df.copy()
    defaults = {
        "training_basic_emotion": "UNRESOLVED",
        "training_label_status": "UNRESOLVED",
        "training_label_tier": "WEAK",
        "training_label_source": "",
        "training_label_provenance": "",
        "training_label_warning": "",
    }
    for key, value in defaults.items():
        if key not in out:
            out[key] = value

    counts = {"exact_class_silver": 0, "non_neutral_silver": 0, "not_promoted": 0}
    for idx, row in out.iterrows():
        decision = str(row["recovery_decision"]).strip()
        phase1 = str(row["phase1_basic_emotion"]).strip()
        exact = str(row.get("recovered_basic_emotion", "")).strip()
        if decision == "EXACT_CLASS_SILVER" and exact:
            label = exact
            counts["exact_class_silver"] += 1
            source = "recovery_v2_exact_class_silver"
            warning = "Machine-derived exact candidate; not human gold."
        elif decision == "NON_NEUTRAL_SILVER" and args.promote_level1_as_provisional_class and phase1:
            label = phase1
            counts["non_neutral_silver"] += 1
            source = "phase1_class_with_recovery_v2_non_neutral_support"
            warning = "Level 1 supports non-neutral presence, not exact emotion identity; Phase 1 class is used provisionally."
        else:
            counts["not_promoted"] += 1
            continue

        out.at[idx, "training_basic_emotion"] = label
        out.at[idx, "training_label_status"] = "MACHINE_PROMOTED"
        out.at[idx, "training_label_tier"] = "PROVISIONAL_MACHINE_GOLD"
        out.at[idx, "training_label_source"] = source
        out.at[idx, "training_label_provenance"] = "machine_only_no_human_review"
        out.at[idx, "training_label_warning"] = warning

    destination = Path(args.output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(destination, index=False)
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "rows_processed": len(out),
        "promotion_flag_enabled": args.promote_level1_as_provisional_class,
        "counts": counts,
        "notes": [
            "This creates a provisional machine-training label, not a human gold label.",
            "human_basic_emotion and original Phase 1/recovery fields are not overwritten.",
            "NON_NEUTRAL_SILVER is promoted as the Phase 1 class only when the explicit opt-in flag is used.",
            "NON_NEUTRAL_SILVER is affect-presence evidence; its exact class remains scientifically unresolved.",
            "Do not use this machine-promoted field as the final evaluation label.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
