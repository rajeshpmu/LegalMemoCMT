#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import pandas as pd


MELD_LABELS = {
    0: "neutral",
    1: "joy",
    2: "surprise",
    3: "sadness",
    4: "anger",
    5: "fear",
    6: "disgust",
}


DEFAULT_NEUTRAL_ERRORS = [
    (0, 1),  # neutral -> joy
    (0, 4),  # neutral -> anger
    (0, 5),  # neutral -> fear
    (0, 2),  # neutral -> surprise
    (3, 0),  # sadness -> neutral
    (1, 0),  # joy -> neutral
    (4, 0),  # anger -> neutral
    (5, 0),  # fear -> neutral
]


def label_name(label: int) -> str:
    return MELD_LABELS.get(int(label), str(label))


def load_metrics(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_predictions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"sample_id", "split", "actual_label", "predicted_label", "confidence", "correct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    df["actual_label"] = df["actual_label"].astype(int)
    df["predicted_label"] = df["predicted_label"].astype(int)
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
    df["correct"] = df["correct"].astype(str).str.lower().isin({"true", "1", "yes"})
    df["actual_name"] = df["actual_label"].map(label_name)
    df["predicted_name"] = df["predicted_label"].map(label_name)
    return df


def load_manifest(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "sample_id" not in df.columns:
        raise ValueError(f"{path} must contain a sample_id column")
    return df


def choose_examples(df: pd.DataFrame, max_examples: int) -> pd.DataFrame:
    chosen_rows = []
    used = set()

    def add_row(row):
        sid = row["sample_id"]
        if sid not in used:
            chosen_rows.append(row)
            used.add(sid)

    correct = df[df["correct"]].sort_values(["confidence", "sample_id"], ascending=[False, True])
    if not correct.empty:
        add_row(correct.iloc[0])

    for actual, pred in DEFAULT_NEUTRAL_ERRORS:
        subset = df[(df["actual_label"] == actual) & (df["predicted_label"] == pred)]
        if not subset.empty:
            subset = subset.sort_values(["confidence", "sample_id"], ascending=[False, True])
            add_row(subset.iloc[0])
        if len(chosen_rows) >= max_examples:
            break

    if len(chosen_rows) < max_examples:
        errors = df[~df["correct"]].sort_values(["confidence", "sample_id"], ascending=[False, True])
        for _, row in errors.iterrows():
            add_row(row)
            if len(chosen_rows) >= max_examples:
                break

    if not chosen_rows:
        return df.head(max_examples).copy()

    return pd.DataFrame(chosen_rows).head(max_examples).copy()


def write_markdown_table(df: pd.DataFrame, path: Path) -> None:
    lines = ["| " + " | ".join(df.columns) + " |", "| " + " | ".join(["---"] * len(df.columns)) + " |"]
    for _, row in df.iterrows():
        values = []
        for value in row.tolist():
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 1 reviewer demo bundle from saved MELD outputs.")
    parser.add_argument("--manifest", required=True, help="Manifest CSV used for the selected fold/run.")
    parser.add_argument("--predictions-csv", required=True, help="Per-sample predictions_test.csv from evaluation.")
    parser.add_argument("--metrics-json", required=True, help="metrics.json for the same run.")
    parser.add_argument("--analysis-dir", required=True, help="analysis_test directory containing confusion matrix and top confusions.")
    parser.add_argument("--output-dir", required=True, help="Where to write the demo bundle.")
    parser.add_argument("--max-examples", type=int, default=5, help="Maximum number of demo examples to include.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    preds_path = Path(args.predictions_csv)
    metrics_path = Path(args.metrics_json)
    analysis_dir = Path(args.analysis_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = load_metrics(metrics_path)
    preds = load_predictions(preds_path)
    manifest = load_manifest(manifest_path)

    merged = preds.merge(manifest, on="sample_id", how="left", suffixes=("", "_manifest"))
    merged["label_name"] = merged["actual_label"].map(label_name)
    merged["predicted_name"] = merged["predicted_label"].map(label_name)
    merged["status"] = merged["correct"].map(lambda x: "correct" if bool(x) else "wrong")

    examples = choose_examples(merged, args.max_examples)
    example_cols = [
        "sample_id",
        "split",
        "label_name",
        "predicted_name",
        "status",
        "confidence",
        "transcript",
        "video_path",
        "audio_path",
    ]
    for col in example_cols:
        if col not in examples.columns:
            examples[col] = ""
    examples = examples[example_cols].copy()
    examples.rename(
        columns={
            "label_name": "ground_truth",
            "predicted_name": "prediction",
            "status": "correct_or_wrong",
        },
        inplace=True,
    )

    metrics_summary = pd.DataFrame(
        [
            ["accuracy", metrics.get("accuracy", "")],
            ["weighted_f1", metrics.get("weighted_f1", "")],
            ["macro_f1", metrics.get("macro_f1", "")],
            ["unweighted_accuracy", metrics.get("unweighted_accuracy", "")],
            ["weighted_accuracy", metrics.get("weighted_accuracy", "")],
            ["num_samples", metrics.get("num_samples", "")],
        ],
        columns=["metric", "value"],
    )
    metrics_summary.to_csv(out_dir / "metrics_summary.csv", index=False)
    write_markdown_table(metrics_summary, out_dir / "metrics_summary.md")

    examples.to_csv(out_dir / "demo_examples.csv", index=False)
    write_markdown_table(examples, out_dir / "demo_examples.md")

    confusion_src = analysis_dir / "confusion_matrix.csv"
    top_confusions_src = analysis_dir / "top_confusions.csv"
    if confusion_src.exists():
        shutil.copy2(confusion_src, out_dir / "confusion_matrix.csv")
    if top_confusions_src.exists():
        shutil.copy2(top_confusions_src, out_dir / "top_confusions.csv")

    readme = out_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Phase 1 Review Demo Bundle",
                "",
                "This bundle is designed for a live reviewer demo.",
                "",
                "Included files:",
                "- `metrics_summary.csv` / `metrics_summary.md`: overall result summary.",
                "- `demo_examples.csv` / `demo_examples.md`: 3 to 5 selected videos for walkthrough.",
                "- `confusion_matrix.csv`: class-by-class error map.",
                "- `top_confusions.csv`: compact error summary.",
                "",
                "Suggested live flow:",
                "1. Start with the highest-confidence correct example.",
                "2. Show a neutral-heavy mistake.",
                "3. Show an emotionally close confusion such as neutral->joy or sadness->neutral.",
                "4. End on the metrics summary and confusion matrix.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Wrote demo bundle to {out_dir}")
    print(f"Examples: {out_dir / 'demo_examples.csv'}")
    print(f"Metrics summary: {out_dir / 'metrics_summary.csv'}")
    print(f"Confusion matrix: {out_dir / 'confusion_matrix.csv' if confusion_src.exists() else 'not copied'}")
    print(f"Top confusions: {out_dir / 'top_confusions.csv' if top_confusions_src.exists() else 'not copied'}")


if __name__ == "__main__":
    main()
