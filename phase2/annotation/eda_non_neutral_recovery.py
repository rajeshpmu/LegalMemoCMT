"""Produce one audit EDA report for the non-neutral recovery output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


COMPONENTS = {
    "phase1_points": "recovery_phase1_points",
    "audio_polarity_points": "recovery_audio_polarity_points",
    "exact_audio_points": "recovery_exact_audio_points",
    "odyssey_points": "recovery_odyssey_points",
    "courtroom_affect_points": "recovery_courtroom_affect_points",
    "visual_points": "recovery_visual_points",
    "penalty": "recovery_penalty",
}


def num(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df.get(column, pd.Series("", index=df.index)), errors="coerce").fillna(0.0)


def phase1_band(value: float) -> str:
    if value < 0.50:
        return "<0.50"
    if value < 0.65:
        return "0.50-<0.65"
    if value < 0.75:
        return "0.65-<0.75"
    if value < 0.85:
        return "0.75-<0.85"
    return ">=0.85"


def compact_records(df: pd.DataFrame) -> list[dict]:
    fields = [
        "utterance_id", "phase1_basic_emotion", "phase1_basic_emotion_confidence",
        "audio_emotion_candidate", "audio_emotion_confidence", "audio_polarity",
        "deberta_target_scope", "semantic_leakage_risk", "recovery_evidence_score",
        "recovery_source_bucket", "recovery_decision", "recovery_reason",
    ]
    fields = [x for x in fields if x in df.columns]
    return df[fields].to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--report-txt", required=True)
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    required = {"utterance_id", "phase1_basic_emotion", "recovery_decision", "recovery_evidence_score"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Input recovery CSV is missing columns: {', '.join(missing)}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = df.copy()
    work["phase1_conf_num"] = num(work, "phase1_basic_emotion_confidence")
    work["recovery_score_num"] = num(work, "recovery_evidence_score")
    work["phase1_band"] = work["phase1_conf_num"].map(phase1_band)
    nonneutral = work[work["phase1_basic_emotion"].str.lower().ne("neutral")].copy()

    band_order = ["<0.50", "0.50-<0.65", "0.65-<0.75", "0.75-<0.85", ">=0.85"]
    decision_order = ["EXACT_CLASS_SILVER", "NON_NEUTRAL_SILVER", "WEAK_UNRESOLVED", "NOT_APPLICABLE"]
    band_counts = nonneutral["phase1_band"].value_counts().reindex(band_order, fill_value=0)
    decision_band = pd.crosstab(nonneutral["recovery_decision"], nonneutral["phase1_band"])
    decision_band = decision_band.reindex(index=decision_order, columns=band_order, fill_value=0)

    original = nonneutral[nonneutral.get("recovery_source_bucket", "").eq("LEVEL_1_ORIGINAL")] if "recovery_source_bucket" in nonneutral else nonneutral.iloc[0:0]
    newly = nonneutral[
        nonneutral.get("recovery_source_bucket", "").eq("WEAK_OR_CONFLICT")
        & nonneutral["recovery_decision"].isin(["EXACT_CLASS_SILVER", "NON_NEUTRAL_SILVER"])
    ] if "recovery_source_bucket" in nonneutral else nonneutral.iloc[0:0]

    weak = nonneutral[nonneutral["recovery_decision"] == "WEAK_UNRESOLVED"].sort_values(
        ["recovery_score_num", "phase1_conf_num"], ascending=False
    )
    top_weak = weak.head(args.top_n)
    near_non_neutral = weak[(weak["recovery_score_num"] >= 3.0) & (weak["recovery_score_num"] < 4.0)].head(args.top_n)
    near_exact = weak[(weak["recovery_score_num"] >= 5.0) & (weak["recovery_score_num"] < 6.0)].head(args.top_n)

    # Write focused CSVs in addition to the human-readable report.
    extracts = {
        "top_weak_closest_to_promotion.csv": top_weak,
        "newly_recovered_rows.csv": newly,
        "top_non_neutral_near_misses.csv": near_non_neutral,
        "top_exact_class_near_misses.csv": near_exact,
        "original_32_ledger.csv": original,
    }
    for filename, subset in extracts.items():
        subset.drop(columns=["phase1_conf_num", "recovery_score_num", "phase1_band"], errors="ignore").to_csv(out_dir / filename, index=False)

    component_frequency = {}
    for name, column in COMPONENTS.items():
        values = num(nonneutral, column)
        component_frequency[name] = {
            "field": column,
            "rows_positive": int((values > 0).sum()),
            "rows_zero": int((values == 0).sum()),
            "sum_points": float(values.sum()),
        }

    failure_counts = (
        weak["recovery_reason"].replace("", "missing_reason").value_counts().to_dict()
        if "recovery_reason" in weak else {}
    )
    score_histogram = work["recovery_score_num"].value_counts().sort_index().to_dict()

    summary = {
        "input_csv": args.input_csv,
        "rows_total": int(len(work)),
        "non_neutral_rows": int(len(nonneutral)),
        "candidate_count_by_phase1_band": {key: int(value) for key, value in band_counts.items()},
        "final_decision_by_phase1_band": {
            str(index): {str(column): int(value) for column, value in row.items()}
            for index, row in decision_band.iterrows()
        },
        "original_level1_rows": {
            "input_count": int(len(original)),
            "retained_as_silver": int(original["recovery_decision"].isin(["EXACT_CLASS_SILVER", "NON_NEUTRAL_SILVER"]).sum()),
            "downgraded_or_unresolved": int((~original["recovery_decision"].isin(["EXACT_CLASS_SILVER", "NON_NEUTRAL_SILVER"])).sum()),
        },
        "newly_recovered_from_weak": {
            "input_pool_count": int((nonneutral.get("recovery_source_bucket", "") == "WEAK_OR_CONFLICT").sum()) if "recovery_source_bucket" in nonneutral else 0,
            "new_silver_count": int(len(newly)),
            "exact_class_count": int((newly["recovery_decision"] == "EXACT_CLASS_SILVER").sum()),
            "non_neutral_count": int((newly["recovery_decision"] == "NON_NEUTRAL_SILVER").sum()),
        },
        "evidence_score_histogram": {str(key): int(value) for key, value in score_histogram.items()},
        "evidence_component_frequency": component_frequency,
        "failure_reason_counts": {str(key): int(value) for key, value in failure_counts.items()},
        "top_20_weak_rows": compact_records(top_weak),
        "all_newly_recovered_rows": compact_records(newly),
        "top_non_neutral_near_misses_score_3_x": compact_records(near_non_neutral),
        "top_exact_class_near_misses_score_5_x": compact_records(near_exact),
        "thresholds": {"non_neutral_score": 4.0, "exact_class_score": 6.0},
        "extract_dir": str(out_dir),
        "notes": [
            "This is read-only EDA over an existing recovery output; it does not alter labels or thresholds.",
            "Near misses are defined as score >=3 and <4 for non-neutral, and >=5 and <6 for exact class.",
            "The recovery score is an auditable screening score, not a calibrated probability.",
        ],
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    def table(title: str, subset: pd.DataFrame) -> str:
        cols = [c for c in ["utterance_id", "phase1_basic_emotion", "phase1_basic_emotion_confidence", "audio_emotion_candidate", "audio_polarity", "recovery_evidence_score", "recovery_decision", "recovery_reason"] if c in subset.columns]
        return title + "\n" + (subset[cols].to_string(index=False) if len(subset) else "(none)")

    report = [
        f"NON-NEUTRAL RECOVERY EDA\nInput: {args.input_csv}\nRows: {len(work)} | Non-neutral: {len(nonneutral)}",
        "\n1. CANDIDATE COUNT BY PHASE1 BAND\n" + band_counts.to_string(),
        "\n2. FINAL DECISION x PHASE1 BAND\n" + decision_band.to_string(),
        f"\n3. ORIGINAL LEVEL-1 ROWS\nInput: {len(original)} | Retained/downgraded: {len(original)-int(original['recovery_decision'].isin(['EXACT_CLASS_SILVER','NON_NEUTRAL_SILVER']).sum()) if len(original) else 0}",
        f"\n4. NEWLY RECOVERED FROM WEAK\nNew rows: {len(newly)}",
        "\n5. EVIDENCE-SCORE HISTOGRAM\n" + pd.Series(score_histogram).sort_index().to_string(),
        "\n6. EVIDENCE-COMPONENT FREQUENCY\n" + pd.DataFrame(component_frequency).T.to_string(),
        "\n7. FAILURE REASON COUNTS\n" + (pd.Series(failure_counts).to_string() if failure_counts else "(none)"),
        table("\n8. TOP WEAK ROWS CLOSEST TO PROMOTION", top_weak),
        table("\n9. ALL NEWLY RECOVERED ROWS", newly),
        table("\nTOP NON-NEUTRAL NEAR MISSES (score = 3.x / threshold 4)", near_non_neutral),
        table("\nTOP EXACT-CLASS NEAR MISSES (score = 5.x / threshold 6)", near_exact),
        "\n10. EXACT-CLASS NEAR MISSES\nSee the score=5.x section above and top_exact_class_near_misses.csv.",
    ]
    report_path = Path(args.report_txt)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n\n".join(report) + "\n")
    print(json.dumps({"summary_json": str(summary_path), "report_txt": str(report_path), "extract_dir": str(out_dir)}, indent=2))


if __name__ == "__main__":
    main()
