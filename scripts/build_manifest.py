from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Build a Phase 1 manifest CSV")
    parser.add_argument("--input-csv", type=str, required=True, help="CSV containing extracted-feature metadata")
    parser.add_argument("--output-csv", type=str, required=True, help="Output manifest CSV")
    parser.add_argument("--root", type=str, default=".", help="Root directory for relative feature paths")
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv)
    required = {"sample_id", "split", "label", "video_feature_path", "audio_feature_path", "transcript"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    root = Path(args.root)
    out = pd.DataFrame(
        {
            "sample_id": df["sample_id"].astype(str),
            "split": df["split"].astype(str),
            "label": df["label"].astype(int),
            "video_path": df["video_feature_path"].map(lambda p: str(root / str(p))),
            "audio_path": df["audio_feature_path"].map(lambda p: str(root / str(p))),
            "transcript": df["transcript"].astype(str),
        }
    )
    out.to_csv(args.output_csv, index=False)
    print(f"Wrote {len(out)} rows to {args.output_csv}")


if __name__ == "__main__":
    main()
