./.venv/bin/python - <<'PY'
import csv
from pathlib import Path

src = Path("data/processed/phase2/clancy/clancy_turn_manifest_post_rejection.csv")
rows = list(csv.DictReader(src.open(newline="", encoding="utf-8")))

bins = {
    "0_8_to_20": lambda d: 0.8 <= d < 20.0,
    "20_to_30": lambda d: 20.0 <= d <= 30.0,
}

for name, predicate in bins.items():
    selected = [
        row for row in rows
        if predicate(float(row.get("clip_duration_seconds") or 0))
    ]

    out = Path(
        f"data/processed/phase2/clancy/clancy_turn_manifest_{name}.csv"
    )

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(selected)

    seconds = sum(
        float(row.get("clip_duration_seconds") or 0)
        for row in selected
    )

    print({
        "output": str(out),
        "rows": len(selected),
        "minutes": round(seconds / 60, 3),
        "hours": round(seconds / 3600, 4),
    })
PY
