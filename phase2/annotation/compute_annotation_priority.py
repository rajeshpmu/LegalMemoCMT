from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import ensure_annotation_schema, load_config, write_json


def numeric(df: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(df.get(column, pd.Series(default, index=df.index)), errors="coerce").fillna(default)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score rows for active annotation review")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)
    df = ensure_annotation_schema(pd.read_csv(args.input_csv, dtype=str).fillna(""))
    weights = cfg.get("priority_weights", {})
    entropy = numeric(df, "prediction_entropy")
    margin = numeric(df, "prediction_margin", 1.0).clip(0, 1)
    disagreement = numeric(df, "modality_disagreement_score")
    rarity = numeric(df, "class_rarity_score")
    uncertainty = 1.0 - margin
    score = (weights.get("entropy", 0.35) * entropy + weights.get("margin", 0.25) * uncertainty + weights.get("modality_disagreement", 0.20) * disagreement + weights.get("class_rarity", 0.10) * rarity)
    quality = df.get("manual_review_required", pd.Series("", index=df.index)).eq("YES")
    score += weights.get("quality_flag", 0.10) * quality.astype(float)
    reasons = []
    for index in df.index:
        parts = []
        if entropy.loc[index] > cfg.get("entropy_threshold", 0.0): parts.append("high_entropy")
        if uncertainty.loc[index] > cfg.get("margin_uncertainty_threshold", 0.0): parts.append("low_margin")
        if disagreement.loc[index] > cfg.get("disagreement_threshold", 0.0): parts.append("modality_disagreement")
        if rarity.loc[index] > cfg.get("rarity_threshold", 0.0): parts.append("class_rarity")
        if quality.loc[index]: parts.append("quality_review")
        reasons.append(";".join(parts) or "control_or_low_priority")
    df["annotation_priority_score"] = score.round(6)
    df["annotation_priority_reason"] = reasons
    df["selection_strategy"] = cfg.get("selection_strategy", "uncertainty_disagreement")
    df["selection_score"] = df["annotation_priority_score"]
    df = df.sort_values("annotation_priority_score", ascending=False)
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    write_json(args.summary_json, {"rows": len(df), "selection_strategy": cfg.get("selection_strategy", "uncertainty_disagreement"), "mean_priority_score": round(float(score.mean()), 6) if len(score) else 0.0, "max_priority_score": round(float(score.max()), 6) if len(score) else 0.0, "fields_used": ["prediction_entropy", "prediction_margin", "modality_disagreement_score", "class_rarity_score", "manual_review_required"], "note": "Weights are configurable and are not validated ground truth."})
    print(f"Wrote priority-scored manifest with {len(df)} rows to {output}")


if __name__ == "__main__":
    main()
