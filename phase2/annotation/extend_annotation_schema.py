from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import ensure_annotation_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Add active-annotation fields without overwriting labels")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    ensure_annotation_schema(df).to_csv(output, index=False)
    print(f"Wrote schema-extended manifest with {len(df)} rows to {output}")


if __name__ == "__main__":
    main()
