from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import ensure_annotation_schema, load_config, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Select a diverse human-reviewed seed set")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    cfg = load_config(args.config)
    target = int(cfg.get("seed_size", 500))
    df = ensure_annotation_schema(pd.read_csv(args.input_csv, dtype=str).fillna("")).drop_duplicates("utterance_id")
    eligible = df.copy()
    if cfg.get("require_witness_speaking"):
        eligible = eligible[(eligible.get("speaker_role", pd.Series("", index=eligible.index)) == "Witness") & (eligible.get("witness_speaking_status", pd.Series("", index=eligible.index)) == "SPEAKING")]
    if eligible.empty:
        raise SystemExit("No eligible rows remain for seed selection")
    rng = eligible.sample(frac=1.0, random_state=args.seed)
    diversity_columns = cfg.get("diversity_columns", ["youtube_id", "witness_id", "examination_phase"])
    available = [column for column in diversity_columns if column in rng.columns]
    if available:
        rng["_seed_group"] = rng[available].fillna("").replace("", "UNKNOWN").astype(str).agg("|".join, axis=1)
    else:
        rng["_seed_group"] = "ALL"
    per_group = max(1, target // max(1, rng["_seed_group"].nunique()))
    selected = pd.concat([group.head(per_group) for _, group in rng.groupby("_seed_group", sort=True)], ignore_index=False).drop_duplicates("utterance_id")
    if len(selected) < target:
        selected = pd.concat([selected, rng.loc[~rng.index.isin(selected.index)].head(target - len(selected))])
    selected = selected.head(target).drop(columns=["_seed_group"], errors="ignore")
    selected["selection_strategy"] = "diversity_seed"
    selected["annotation_iteration"] = "0"
    selected["basic_emotion_annotation_status"] = "UNLABELED"
    selected["courtroom_affect_annotation_status"] = "UNLABELED"
    selected["manual_review_required"] = "YES"
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(output, index=False)
    write_json(args.summary_json, {"input_rows": len(df), "eligible_rows": len(eligible), "selected_rows": len(selected), "target_rows": target, "selection_strategy": "diversity_seed", "diversity_columns": available, "seed": args.seed})
    print(f"Wrote {len(selected)} seed rows to {output}")


if __name__ == "__main__":
    main()
