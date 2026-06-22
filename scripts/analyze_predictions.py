#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
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

CREMA_D_LABELS = {
    0: "anger",
    1: "disgust",
    2: "fear",
    3: "happy",
    4: "neutral",
    5: "sad",
}


def label_map(dataset: str) -> dict[int, str]:
    dataset = dataset.strip().lower()
    if dataset == "meld":
        return MELD_LABELS
    if dataset in {"crema_d", "crema-d", "crema"}:
        return CREMA_D_LABELS
    raise ValueError(f"Unsupported dataset '{dataset}'. Use meld or crema_d.")


def build_confusion_matrix(df: pd.DataFrame, classes: list[int]) -> pd.DataFrame:
    matrix = pd.DataFrame(0, index=classes, columns=classes, dtype=int)
    for _, row in df.iterrows():
        actual = int(row["actual_label"])
        pred = int(row["predicted_label"])
        if actual in matrix.index and pred in matrix.columns:
            matrix.loc[actual, pred] += 1
    return matrix


def write_markdown_table(df: pd.DataFrame, path: Path) -> None:
    """Write a simple GitHub-flavored Markdown table without tabulate."""
    lines: list[str] = []
    headers = [str(col) for col in df.columns]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for _, row in df.iterrows():
        values = []
        for value in row.tolist():
            if isinstance(value, float):
                values.append(f"{value:.6f}".rstrip("0").rstrip("."))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create prediction summary tables and confusion matrix")
    parser.add_argument("--predictions-csv", type=str, required=True, help="Input predictions.csv")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory for generated reports")
    parser.add_argument("--dataset", type=str, default="crema_d", help="Label mapping dataset: meld or crema_d")
    parser.add_argument("--top-n", type=int, default=20, help="Number of rows to include in the summary table")
    parser.add_argument("--sort", type=str, default="original", choices=["original", "confidence", "correct"], help="Sort order for the summary table")
    parser.add_argument("--split", type=str, default="", help="Optional split filter (e.g. train, dev, test)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.predictions_csv)
    if df.empty:
        raise ValueError(f"{args.predictions_csv} contains no rows")

    required = {"sample_id", "split", "actual_label", "predicted_label", "confidence", "correct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{args.predictions_csv} is missing columns: {sorted(missing)}")

    if args.split.strip():
        wanted_split = args.split.strip().lower()
        df = df[df["split"].astype(str).str.lower() == wanted_split].copy()
        if df.empty:
            raise ValueError(f"No rows found for split '{wanted_split}' in {args.predictions_csv}")

    label_names = label_map(args.dataset)
    df["actual_name"] = df["actual_label"].astype(int).map(label_names)
    df["predicted_name"] = df["predicted_label"].astype(int).map(label_names)
    df["correct"] = df["correct"].astype(str).str.lower().isin({"true", "1", "yes"})
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")

    if args.sort == "confidence":
        table = df.sort_values(["confidence", "sample_id"], ascending=[False, True]).head(args.top_n)
    elif args.sort == "correct":
        table = df.sort_values(["correct", "confidence", "sample_id"], ascending=[False, False, True]).head(args.top_n)
    else:
        table = df.head(args.top_n)

    summary_cols = [
        "sample_id",
        "split",
        "actual_label",
        "actual_name",
        "predicted_label",
        "predicted_name",
        "confidence",
        "correct",
    ]
    summary = table[summary_cols].copy()

    summary_csv = out_dir / "predicted_vs_actual_first20.csv"
    summary_md = out_dir / "predicted_vs_actual_first20.md"
    summary.to_csv(summary_csv, index=False)
    write_markdown_table(summary, summary_md)

    classes = sorted(label_names)
    cm = build_confusion_matrix(df, classes)
    cm.index = [f"{c}:{label_names[c]}" for c in cm.index]
    cm.columns = [f"{c}:{label_names[c]}" for c in cm.columns]
    cm_csv = out_dir / "confusion_matrix.csv"
    cm.to_csv(cm_csv)

    # Human-readable confusion summary: top off-diagonal confusions.
    confusion_rows: list[dict[str, object]] = []
    for actual in classes:
        for pred in classes:
            if actual == pred:
                continue
            count = int((df["actual_label"].astype(int).eq(actual) & df["predicted_label"].astype(int).eq(pred)).sum())
            if count > 0:
                confusion_rows.append(
                    {
                        "actual_label": actual,
                        "actual_name": label_names[actual],
                        "predicted_label": pred,
                        "predicted_name": label_names[pred],
                        "count": count,
                    }
                )
    confusion_summary = pd.DataFrame(confusion_rows).sort_values("count", ascending=False) if confusion_rows else pd.DataFrame(
        columns=["actual_label", "actual_name", "predicted_label", "predicted_name", "count"]
    )
    confusion_summary_csv = out_dir / "top_confusions.csv"
    confusion_summary.to_csv(confusion_summary_csv, index=False)

    report_lines = [
        f"Predictions file: {args.predictions_csv}",
        f"Dataset mapping: {args.dataset}",
        f"Rows: {len(df)}",
        f"Summary table: {summary_csv}",
        f"Summary markdown: {summary_md}",
        f"Confusion matrix CSV: {cm_csv}",
        f"Top confusions CSV: {confusion_summary_csv}",
    ]
    (out_dir / "report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Wrote summary table to {summary_csv}")
    print(f"Wrote markdown table to {summary_md}")
    print(f"Wrote confusion matrix to {cm_csv}")
    print(f"Wrote top confusions to {confusion_summary_csv}")


if __name__ == "__main__":
    main()
