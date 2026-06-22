from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a smaller manifest for smoke training runs")
    parser.add_argument("--manifest", type=str, required=True, help="Input manifest CSV")
    parser.add_argument("--output", type=str, required=True, help="Output subset manifest CSV")
    parser.add_argument("--per-split", type=int, default=50, help="Max rows to keep per split")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    in_path = Path(args.manifest)
    out_path = Path(args.output)
    if not in_path.exists():
        raise FileNotFoundError(f"Input manifest not found: {in_path}")

    df = pd.read_csv(in_path)
    required = {"sample_id", "split", "label", "video_path", "audio_path", "transcript"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Manifest missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError("Manifest contains no rows")

    parts = []
    for split, group in df.groupby("split", dropna=False):
        n = min(len(group), args.per_split)
        sample = group.sample(n=n, random_state=args.seed, replace=False) if n > 0 else group.head(0)
        parts.append(sample)

    out_df = pd.concat(parts, ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"Wrote subset manifest with {len(out_df)} rows to {out_path}")
    print(f"Rows per split capped at {args.per_split}")


if __name__ == "__main__":
    main()
