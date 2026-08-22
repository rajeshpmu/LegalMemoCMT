from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


DEFAULT_INPUT = Path("data/processed/phase2/clancy/clancy_utterance_manifest.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/clancy/clancy_dataset_manifest.csv")
DEFAULT_TRAIN = Path("data/processed/phase2/clancy/train.csv")
DEFAULT_DEV = Path("data/processed/phase2/clancy/dev.csv")
DEFAULT_TEST = Path("data/processed/phase2/clancy/test.csv")
DEFAULT_SUMMARY = Path("reports/phase2/clancy_dataset_split_summary.json")
DEFAULT_EXCLUSIONS = Path("data/processed/phase2/clancy/clancy_turn_rejection_manifest.csv")


def _group_rows(rows: list[dict[str, str]], group_column: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        group_id = (row.get(group_column) or "").strip() or "UNASSIGNED"
        grouped[group_id].append(row)
    return grouped


def _load_exclusion_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    import csv
    with path.open(newline="", encoding="utf-8") as f:
        return {
            (row.get("turn_id") or row.get("utterance_id") or "").strip()
            for row in csv.DictReader(f)
            if (row.get("turn_id") or row.get("utterance_id") or "").strip()
        }


def _split_groups(
    grouped: dict[str, list[dict[str, str]]],
    *,
    train_ratio: float,
    dev_ratio: float,
    test_ratio: float,
) -> dict[str, str]:
    total_rows = sum(len(v) for v in grouped.values())
    targets = {
        "train": total_rows * train_ratio,
        "dev": total_rows * dev_ratio,
        "test": total_rows * test_ratio,
    }
    current = {"train": 0.0, "dev": 0.0, "test": 0.0}
    assignment: dict[str, str] = {}
    for group_id, group_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        size = float(len(group_rows))
        split = min(
            ("train", "dev", "test"),
            key=lambda candidate: (current[candidate] + size - targets[candidate], current[candidate], candidate),
        )
        assignment[group_id] = split
        current[split] += size
    return assignment


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a split-aware Clancy dataset manifest")
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--train-csv", default=str(DEFAULT_TRAIN))
    parser.add_argument("--dev-csv", default=str(DEFAULT_DEV))
    parser.add_argument("--test-csv", default=str(DEFAULT_TEST))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--group-column", default="youtube_id", help="Column that defines the leakage group")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--dev-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--usable-column", default="usable_for_phase2", help="Column used to keep usable rows")
    parser.add_argument("--usable-value", default="YES", help="Value treated as usable")
    parser.add_argument("--exclusion-csv", default=str(DEFAULT_EXCLUSIONS), help="Rows excluded from dataset selection")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.input_csv))
    exclusion_ids = _load_exclusion_ids(Path(args.exclusion_csv))
    usable_rows = [
        row for row in rows
        if row.get(args.usable_column, "").strip().upper() == args.usable_value.upper()
        and (row.get("turn_id") or row.get("utterance_id") or "").strip() not in exclusion_ids
    ]
    if not usable_rows:
        raise SystemExit(f"No usable rows found in {args.input_csv}")

    grouped = _group_rows(usable_rows, args.group_column)
    assignment = _split_groups(
        grouped,
        train_ratio=args.train_ratio,
        dev_ratio=args.dev_ratio,
        test_ratio=args.test_ratio,
    )

    output_rows: list[dict[str, Any]] = []
    split_rows = {"train": [], "dev": [], "test": []}
    for group_id, group_rows in grouped.items():
        split = assignment[group_id]
        for row in group_rows:
            enriched = dict(row)
            enriched["split_group_id"] = group_id
            enriched["split_strategy"] = f"group_by_{args.group_column}"
            enriched["split"] = split
            output_rows.append(enriched)
            split_rows[split].append(enriched)

    output_rows.sort(key=lambda row: (row.get("split", ""), row.get("split_group_id", ""), row.get("utterance_id", "")))
    for split in split_rows:
        split_rows[split].sort(key=lambda row: (row.get("split_group_id", ""), row.get("utterance_id", "")))

    output_csv = Path(args.output_csv)
    train_csv = Path(args.train_csv)
    dev_csv = Path(args.dev_csv)
    test_csv = Path(args.test_csv)
    summary_json = Path(args.summary_json)
    for path in [output_csv, train_csv, dev_csv, test_csv, summary_json]:
        ensure_dir(path.parent)

    fieldnames = list(output_rows[0].keys())
    write_csv(output_csv, output_rows, fieldnames)
    write_csv(train_csv, split_rows["train"], fieldnames)
    write_csv(dev_csv, split_rows["dev"], fieldnames)
    write_csv(test_csv, split_rows["test"], fieldnames)

    split_counts = {split: len(items) for split, items in split_rows.items()}
    split_hours = {
        split: round(sum(float(row.get("duration_seconds") or 0) for row in items) / 3600.0, 4)
        for split, items in split_rows.items()
    }
    split_group_counts = {split: len({row.get(args.group_column, "") for row in items}) for split, items in split_rows.items()}
    summary = {
        "input_csv": str(args.input_csv),
        "exclusion_csv": str(Path(args.exclusion_csv)),
        "excluded_rows": sum(
            1 for row in rows
            if (row.get("turn_id") or row.get("utterance_id") or "").strip() in exclusion_ids
        ),
        "output_csv": str(output_csv),
        "train_csv": str(train_csv),
        "dev_csv": str(dev_csv),
        "test_csv": str(test_csv),
        "total_rows": len(output_rows),
        "usable_rows": len(usable_rows),
        "group_column": args.group_column,
        "total_groups": len(grouped),
        "split_counts": split_counts,
        "split_hours": split_hours,
        "split_group_counts": split_group_counts,
        "split_ratios": {"train": args.train_ratio, "dev": args.dev_ratio, "test": args.test_ratio},
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
