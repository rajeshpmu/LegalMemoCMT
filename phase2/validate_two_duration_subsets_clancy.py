./.venv/bin/python - <<'PY'
import csv
from pathlib import Path

files = [
    "data/processed/phase2/clancy/clancy_turn_manifest_0_8_to_20.csv",
    "data/processed/phase2/clancy/clancy_turn_manifest_20_to_30.csv",
]

for filename in files:
    rows = list(csv.DictReader(open(filename, newline="", encoding="utf-8")))
    missing_video = 0
    missing_audio = 0
    bad_duration = 0

    for row in rows:
        if not Path(row["clip_video_path"]).exists():
            missing_video += 1
        if not Path(row["clip_audio_path"]).exists():
            missing_audio += 1

        duration = float(row.get("clip_duration_seconds") or 0)

        if "0_8_to_20" in filename and not 0.8 <= duration < 20:
            bad_duration += 1
        if "20_to_30" in filename and not 20 <= duration <= 30:
            bad_duration += 1

    print({
        "file": filename,
        "rows": len(rows),
        "missing_video": missing_video,
        "missing_audio": missing_audio,
        "bad_duration_rows": bad_duration,
    })
PY
