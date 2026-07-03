from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir
else:
    from .common import ensure_dir


def _norm(text: object) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate Phase 2 candidate ledgers by case identity")
    parser.add_argument(
        "--input-csv",
        nargs="+",
        default=["data/phase2/source_manifests/case_candidate_ledger.csv", "data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv"],
        help="One or more candidate ledger CSVs to merge",
    )
    parser.add_argument("--output-csv", default="data/phase2/source_manifests/case_candidate_ledger_deduped.csv", help="Output deduplicated ledger")
    args = parser.parse_args()

    frames = [pd.read_csv(path) for path in args.input_csv]
    df = pd.concat(frames, ignore_index=True, sort=False)
    if df.empty:
        raise SystemExit("No rows found in input ledgers")

    for col in ["case_number", "case_family", "tribunal"]:
        if col not in df.columns:
            df[col] = ""

    df["_case_number_norm"] = df["case_number"].map(_norm)
    df["_case_family_norm"] = df["case_family"].map(_norm)
    df["_tribunal_norm"] = df["tribunal"].map(_norm)

    df["_dedup_key"] = (
        df["_tribunal_norm"].fillna("")
        + "::"
        + df["_case_number_norm"].fillna("")
        + "::"
        + df["_case_family_norm"].fillna("")
    )

    # Prefer rows that have more evidence and more complete annotations.
    priority_rank = {
        "yes": 3,
        "yes_after_link_validation": 2,
        "unknown": 1,
        "no": 0,
        "": 0,
    }

    def _score(row: pd.Series) -> tuple[int, int, int, int]:
        has_video = _norm(row.get("has_video"))
        include_flag = _norm(row.get("include_in_tri_modal_set"))
        tap_count = _norm(row.get("tap_count"))
        evidence = 0
        if "video" in has_video:
            evidence += 3
        evidence += priority_rank.get(include_flag, 0)
        evidence += 2 if "confirmed" in has_video else 0
        evidence += 1 if tap_count and tap_count not in {"unknown", "tbd"} else 0
        completeness = sum(1 for c in ["notes", "source_url", "inventory_search_url"] if _norm(row.get(c)))
        return (evidence, completeness, len(_norm(row.get("notes"))), len(_norm(row.get("source_url"))))

    df["_score"] = df.apply(_score, axis=1)
    df = df.sort_values(by=["_dedup_key", "_score"], ascending=[True, False])
    deduped = df.drop_duplicates(subset=["_dedup_key"], keep="first").copy()

    drop_cols = [c for c in deduped.columns if c.startswith("_")]
    deduped = deduped.drop(columns=drop_cols)
    ensure_dir(Path(args.output_csv).parent)
    deduped.to_csv(args.output_csv, index=False)

    print(f"Input rows: {len(df)}")
    print(f"Deduped rows: {len(deduped)}")
    print(f"Wrote deduplicated ledger to {args.output_csv}")


if __name__ == "__main__":
    main()
