from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistently exclude complete Clancy source videos from corpus use")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--source-ids", required=True, help="Comma-separated youtube/source IDs")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if "youtube_id" not in df.columns:
        raise SystemExit("Input manifest must contain youtube_id")
    source_ids = {value.strip() for value in args.source_ids.split(",") if value.strip()}
    if not source_ids:
        raise SystemExit("No source IDs supplied")
    matched = df["youtube_id"].isin(source_ids)
    for column, default in {
        "corpus_exclusion_status": "",
        "corpus_exclusion_reason": "",
    }.items():
        if column not in df.columns:
            df[column] = default
    df.loc[matched, "corpus_exclusion_status"] = "EXCLUDE"
    df.loc[matched, "corpus_exclusion_reason"] = args.reason

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    print(f"Excluded {int(matched.sum())} rows from {sorted(source_ids)}")
    print(f"Wrote {len(df)} rows to {output}")
    missing = sorted(source_ids - set(df.loc[matched, "youtube_id"]))
    if missing:
        print(f"WARNING: source IDs not found in input: {missing}")


if __name__ == "__main__":
    main()
