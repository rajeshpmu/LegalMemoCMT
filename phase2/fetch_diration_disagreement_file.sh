./.venv/bin/python - <<'PY'
import pandas as pd

src = "data/processed/phase2/clancy/emotion_scope_review_full_deberta_comparison.csv"
out = "data/processed/phase2/clancy/emotion_scope_full_disagreement_duration_review.csv"

df = pd.read_csv(src, dtype=str).fillna("")
df["duration"] = pd.to_numeric(df["clip_duration_seconds"], errors="coerce").fillna(0)

review = df[
    (df["target_scope_disagreement"] == "YES")
    | (df["duration"] < 0.8)
    | (df["duration"] > 30)
].copy()

review.to_csv(out, index=False)
print("Review rows:", len(review))
print("Written:", out)
PY
