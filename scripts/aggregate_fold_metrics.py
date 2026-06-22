from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev


METRIC_KEYS = [
    "accuracy",
    "weighted_accuracy",
    "unweighted_accuracy",
    "macro_f1",
    "weighted_f1",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate fold metrics JSON files")
    parser.add_argument("--input-dir", type=str, required=True, help="Directory containing per-fold metrics JSON files")
    parser.add_argument("--pattern", type=str, default="fold_*/metrics.json", help="Glob pattern relative to input-dir")
    parser.add_argument("--output-json", type=str, default="", help="Optional summary JSON path")
    parser.add_argument("--output-md", type=str, default="", help="Optional summary markdown path")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    files = sorted(input_dir.glob(args.pattern))
    if not files:
        raise FileNotFoundError(f"No metrics files found under {input_dir} matching {args.pattern}")

    rows = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append((path, data))

    summary = {
        "input_dir": str(input_dir),
        "pattern": args.pattern,
        "num_folds": len(rows),
        "metrics": {},
    }
    for key in METRIC_KEYS:
        values = [float(data[key]) for _, data in rows if key in data]
        if not values:
            continue
        summary["metrics"][key] = {
            "mean": mean(values),
            "std": pstdev(values) if len(values) > 1 else 0.0,
            "values": values,
        }

    if args.output_json:
        out_json = Path(args.output_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote summary JSON to {out_json}")

    if args.output_md:
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Fold Metrics Summary", "", f"- Input dir: `{input_dir}`", f"- Folds: `{len(rows)}`", ""]
        lines.append("| Metric | Mean | Std | Values |")
        lines.append("|---|---:|---:|---|")
        for key, stats in summary["metrics"].items():
            values = ", ".join(f"{v:.4f}" for v in stats["values"])
            lines.append(f"| {key} | {stats['mean']:.4f} | {stats['std']:.4f} | {values} |")
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote summary markdown to {out_md}")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
