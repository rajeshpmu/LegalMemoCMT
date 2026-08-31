"""Build a final machine-training manifest from accepted machine tiers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True, help="Machine-promoted manifest containing both gate layers")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if "utterance_id" not in df:
        raise SystemExit("Input manifest requires utterance_id")
    out = df.copy()

    auto = out.get("machine_annotation_status", pd.Series("", index=out.index)).eq("AUTO_ADJUDICATED")
    provisional = out.get("training_label_status", pd.Series("", index=out.index)).eq("MACHINE_PROMOTED")
    selected = auto | provisional
    final = out.loc[selected].copy()

    final["final_training_basic_emotion"] = "UNRESOLVED"
    final["final_training_label_status"] = "UNRESOLVED"
    final["final_training_label_tier"] = "WEAK"
    final["final_training_label_source"] = ""
    final["final_training_label_provenance"] = ""
    final["final_training_label_warning"] = ""

    # Prefer explicit machine-promoted labels if a row belongs to that layer.
    promoted_mask = final.get("training_label_status", pd.Series("", index=final.index)).eq("MACHINE_PROMOTED")
    final.loc[promoted_mask, "final_training_basic_emotion"] = final.loc[promoted_mask, "training_basic_emotion"]
    final.loc[promoted_mask, "final_training_label_status"] = "PROVISIONAL_MACHINE_GOLD"
    final.loc[promoted_mask, "final_training_label_tier"] = final.loc[promoted_mask, "training_label_tier"]
    final.loc[promoted_mask, "final_training_label_source"] = final.loc[promoted_mask, "training_label_source"]
    final.loc[promoted_mask, "final_training_label_provenance"] = "machine_only_no_human_review"
    final.loc[promoted_mask, "final_training_label_warning"] = final.loc[promoted_mask, "training_label_warning"]

    auto_only = ~promoted_mask & auto.loc[final.index]
    # Neutral auto-gate fields vary by gate version; keep a deterministic fallback.
    neutral_label = final.get("machine_final_basic_emotion", pd.Series("", index=final.index))
    neutral_label = neutral_label.mask(neutral_label.eq(""), final.get("final_basic_emotion", pd.Series("", index=final.index)))
    final.loc[auto_only, "final_training_basic_emotion"] = neutral_label.loc[auto_only].replace("", "neutral")
    final.loc[auto_only, "final_training_label_status"] = "AUTO_ADJUDICATED"
    final.loc[auto_only, "final_training_label_tier"] = "SILVER"
    final.loc[auto_only, "final_training_label_source"] = "neutral_machine_acceptance_gate"
    final.loc[auto_only, "final_training_label_provenance"] = "machine_only_no_human_review"
    final.loc[auto_only, "final_training_label_warning"] = "Machine-assisted neutral label; not human gold."

    final["final_training_selection_reason"] = ""
    final.loc[promoted_mask, "final_training_selection_reason"] = "PROVISIONAL_MACHINE_GOLD from recovery output"
    final.loc[auto_only, "final_training_selection_reason"] = "AUTO_ADJUDICATED neutral machine gate"
    final = final[final["final_training_basic_emotion"].ne("UNRESOLVED")].copy()

    destination = Path(args.output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(destination, index=False)
    summary = {
        "input_csv": args.input_csv,
        "output_csv": args.output_csv,
        "input_rows": len(df),
        "selected_rows_before_label_check": int(selected.sum()),
        "rows_written": len(final),
        "auto_adjudicated_rows": int(auto_only.sum()),
        "provisional_machine_gold_rows": int(promoted_mask.sum()),
        "final_training_label_counts": final["final_training_basic_emotion"].value_counts().to_dict(),
        "final_training_status_counts": final["final_training_label_status"].value_counts().to_dict(),
        "notes": [
            "This is a machine-training manifest, not a human-gold evaluation manifest.",
            "Original, Phase 1, audio, scope, recovery, and human fields are preserved.",
            "PROVISIONAL_MACHINE_GOLD includes explicitly opted-in machine promotions.",
            "AUTO_ADJUDICATED rows come from the neutral machine gate.",
            "Use a separate human-validated test set for final evaluation.",
        ],
    }
    report = Path(args.summary_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
