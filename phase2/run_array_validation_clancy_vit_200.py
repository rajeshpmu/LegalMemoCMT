./.venv/bin/python - <<'PY'
import csv
import numpy as np

p = "data/processed/phase2/clancy/duration_0_8_to_20/clancy_dataset_manifest_vit_200.csv"

with open(p, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

assert len(rows) == 200

for row in rows:
    arr = np.load(row["video_features_path"], allow_pickle=False)
    assert arr.shape == (16, 768)
    assert arr.dtype == np.float32
    assert np.isfinite(arr).all()

print("PASS:", len(rows), "valid embeddings")
PY
