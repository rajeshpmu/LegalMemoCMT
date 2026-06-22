from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare benchmark metrics from saved JSON files")
    parser.add_argument("--meld-metrics", type=str, required=True, help="Path to MELD metrics JSON")
    parser.add_argument("--crema-metrics", type=str, required=True, help="Path to CREMA-D metrics JSON")
    args = parser.parse_args()

    meld = json.loads(Path(args.meld_metrics).read_text(encoding="utf-8"))
    crema = json.loads(Path(args.crema_metrics).read_text(encoding="utf-8"))

    print("MELD:", meld)
    print("CREMA-D:", crema)

    def score(m):
        return float(m.get("weighted_accuracy", m.get("weighted_f1", 0.0)))

    better = "MELD" if score(meld) >= score(crema) else "CREMA-D"
    print(f"Better weighted_accuracy: {better}")


if __name__ == "__main__":
    main()
