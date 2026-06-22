from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd


def run_analysis(predictions_csv: Path, output_dir: Path) -> None:
    subprocess.run(
        [
            "python3",
            "scripts/analyze_predictions.py",
            "--predictions-csv",
            str(predictions_csv),
            "--output-dir",
            str(output_dir),
            "--dataset",
            "meld",
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze existing MELD CV fold predictions")
    parser.add_argument(
        "--root",
        type=str,
        default="results/paper_aligned_meld_cv/cmt_min",
        help="Root directory containing fold_*/predictions_test.csv",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="results/paper_aligned_meld_cv/cmt_min/fold_summary.json",
        help="Path to aggregate summary JSON",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="results/paper_aligned_meld_cv/cmt_min/fold_summary.md",
        help="Path to aggregate summary markdown",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(root)

    summaries: list[dict[str, object]] = []
    for fold_dir in sorted(root.glob("fold_*")):
        pred = fold_dir / "predictions_test.csv"
        if not pred.exists():
            continue
        out_dir = fold_dir / "analysis_test"
        run_analysis(pred, out_dir)
        metrics_path = fold_dir / "metrics.json"
        metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
        summaries.append(
            {
                "fold": fold_dir.name,
                "metrics": metrics,
                "predictions_csv": str(pred),
                "analysis_dir": str(out_dir),
            }
        )

    if not summaries:
        raise RuntimeError(f"No fold predictions found under {root}")

    df = pd.DataFrame(
        [
            {
                "fold": s["fold"],
                "accuracy": s["metrics"].get("accuracy"),
                "weighted_accuracy": s["metrics"].get("weighted_accuracy"),
                "unweighted_accuracy": s["metrics"].get("unweighted_accuracy"),
                "macro_f1": s["metrics"].get("macro_f1"),
                "weighted_f1": s["metrics"].get("weighted_f1"),
                "num_samples": s["metrics"].get("num_samples"),
            }
            for s in summaries
        ]
    )
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summaries, indent=2), encoding="utf-8")

    out_md = Path(args.output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(
        "# MELD CV Fold Summary\n\n" + df.to_markdown(index=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote aggregate summary to {out_json}")
    print(f"Wrote aggregate markdown to {out_md}")


if __name__ == "__main__":
    main()
