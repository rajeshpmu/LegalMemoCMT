from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score(metrics: dict) -> float:
    return float(metrics.get("weighted_accuracy", metrics.get("weighted_f1", 0.0)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare MemoCMT-style experiment results")
    parser.add_argument("--results", nargs="+", required=True, help="Pairs of name=path/to/metrics.json")
    args = parser.parse_args()

    rows = []
    for item in args.results:
        name, path = item.split("=", 1)
        rows.append((name, load_json(path)))

    for name, data in rows:
        print(name, data)

    best = max(rows, key=lambda item: score(item[1]))
    print(f"Best weighted_accuracy: {best[0]}")


if __name__ == "__main__":
    main()
