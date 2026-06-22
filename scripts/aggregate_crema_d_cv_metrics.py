from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev


METRIC_KEYS = [
    ("weighted_accuracy", "W-Acc"),
    ("unweighted_accuracy", "UW-Acc"),
    ("macro_f1", "Macro-F1"),
    ("weighted_f1", "Weighted-F1"),
]


def aggregate(values: list[float]) -> dict[str, object]:
    return {
        "mean": mean(values),
        "std": pstdev(values) if len(values) > 1 else 0.0,
        "values": values,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate CREMA-D CV metrics")
    parser.add_argument("--input-dir", type=str, required=True, help="Directory containing fold_* metric JSON files")
    parser.add_argument("--pattern", type=str, default="fold_*/metrics.json", help="Glob pattern for metric files")
    parser.add_argument("--output-json", type=str, required=True, help="Path to write summary JSON")
    parser.add_argument("--output-md", type=str, required=True, help="Path to write summary markdown")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    metric_paths = sorted(input_dir.glob(args.pattern))
    if not metric_paths:
        raise ValueError(f"No metric files found in {input_dir} using pattern {args.pattern}")

    rows = []
    for path in metric_paths:
        fold_name = path.parent.name
        metrics = json.loads(path.read_text(encoding="utf-8"))
        row = {"fold": fold_name}
        for key, _ in METRIC_KEYS:
            if key not in metrics:
                raise ValueError(f"{path} is missing metric '{key}'")
            row[key] = float(metrics[key])
        rows.append(row)

    summary = {
        "input_dir": str(input_dir),
        "pattern": args.pattern,
        "num_folds": len(rows),
        "metrics": {},
        "folds": rows,
    }
    for key, pretty in METRIC_KEYS:
        summary["metrics"][key] = aggregate([row[key] for row in rows])
        summary["metrics"][key]["label"] = pretty

    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_lines = [
        "# CREMA-D Cross-Validation Summary",
        "",
        f"- Input dir: `{input_dir}`",
        f"- Pattern: `{args.pattern}`",
        f"- Number of folds: `{len(rows)}`",
        "",
        "| Metric | Mean | Std |",
        "| --- | ---: | ---: |",
    ]
    for key, pretty in METRIC_KEYS:
        stat = summary["metrics"][key]
        md_lines.append(f"| {pretty} | {stat['mean']:.4f} | {stat['std']:.4f} |")
    md_lines.append("")
    md_lines.append("## Fold Values")
    md_lines.append("")
    md_lines.append("| Fold | W-Acc | UW-Acc | Macro-F1 | Weighted-F1 |")
    md_lines.append("| --- | ---: | ---: | ---: | ---: |")
    for row in rows:
        md_lines.append(
            f"| {row['fold']} | {row['weighted_accuracy']:.4f} | {row['unweighted_accuracy']:.4f} | "
            f"{row['macro_f1']:.4f} | {row['weighted_f1']:.4f} |"
        )

    out_md = Path(args.output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Wrote summary JSON to {out_json}")
    print(f"Wrote summary markdown to {out_md}")


if __name__ == "__main__":
    main()
