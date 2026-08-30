./.venv/bin/python - <<'PY'
import pandas as pd

src = "data/processed/phase2/clancy/emotion_scope_fused_training_manifest_full.csv"
out = "data/processed/phase2/clancy/emotion_scope_fused_training_critical_review.csv"

df = pd.read_csv(src, dtype=str).fillna("")
critical = df[df["scope_fusion_critical_conflict"] == "YES"].copy()
critical.to_csv(out, index=False)

print("Critical rows:", len(critical))
print("Written:", out)
PY
