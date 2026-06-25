from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .common import ensure_dir, group_case_splits


def main() -> None:
    parser = argparse.ArgumentParser(description="Add train/dev/test splits to the Phase 2 legal dataset manifest")
    parser.add_argument(
        "--input-csv",
        type=str,
        default="data/processed/phase2/legalmemocmt_phase2_dataset.csv",
        help="Input Phase 2 dataset CSV",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default="data/processed/phase2/legalmemocmt_phase2_dataset_split.csv",
        help="Output CSV with a split column",
    )
    parser.add_argument(
        "--group-by",
        type=str,
        default="manifest_id",
        choices=["manifest_id", "case_name", "tribunal"],
        help="Column used to keep related utterances in the same split",
    )
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--dev-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    output_csv = Path(args.output_csv)
    if not input_csv.exists():
        raise FileNotFoundError(f"Input Phase 2 dataset not found: {input_csv}")

    df = pd.read_csv(input_csv)
    if df.empty:
        raise ValueError("Input Phase 2 dataset is empty")

    if "split" in df.columns and df["split"].astype(str).str.strip().any():
        ensure_dir(output_csv.parent)
        df.to_csv(output_csv, index=False)
        print(f"Input already contains split values. Copied to {output_csv}")
        return

    if args.group_by not in df.columns:
        raise ValueError(f"Grouping column not found in dataset: {args.group_by}")

    group_ids = df[args.group_by].fillna("").astype(str).tolist()
    split_map = group_case_splits(
        group_ids,
        train_ratio=args.train_ratio,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
    )

    df = df.copy()
    df["split"] = [split_map.get(str(value), "train") for value in group_ids]
    ensure_dir(output_csv.parent)
    df.to_csv(output_csv, index=False)

    print(f"Wrote split manifest to {output_csv}")
    print(f"Rows: {len(df)}")
    print(f"Split counts: {df['split'].value_counts(dropna=False).to_dict()}")
    print(f"Grouping column: {args.group_by}")


if __name__ == "__main__":
    main()
