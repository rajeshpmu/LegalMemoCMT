./.venv/bin/python - <<'PY'
import pandas as pd

p = "data/processed/phase2/clancy/emotion_scope_fused_training_manifest_full.csv"
df = pd.read_csv(p, dtype=str).fillna("")

print(
    df[df["scope_fusion_critical_conflict"] == "YES"]
    ["scope_fusion_reason"]
    .value_counts()
    .to_string()
)
PY
