./.venv/bin/python - <<'PY'
import pandas as pd

p = "data/processed/phase2/clancy/emotion_scope_review_full_deberta_comparison.csv"
df = pd.read_csv(p, dtype=str).fillna("")

duration_col = next(
    c for c in ["clip_duration_seconds", "duration_seconds", "turn_duration_seconds"]
    if c in df.columns
)

df["duration_seconds_num"] = pd.to_numeric(
    df[duration_col], errors="coerce"
).fillna(0)

df["disagreement_group"] = df["target_scope_disagreement"].replace(
    {"YES": "DISAGREEMENT", "NO": "AGREEMENT", "": "UNKNOWN"}
)

df["duration_band"] = pd.cut(
    df["duration_seconds_num"],
    bins=[-float("inf"), 0.8, 20, 30, float("inf")],
    labels=["<0.8", "0.8-<20", "20-30", ">30"],
    right=False
)

summary = (
    df.groupby(["disagreement_group", "duration_band"], observed=False)
      .agg(
          rows=("utterance_id", "count"),
          total_minutes=("duration_seconds_num", lambda x: x.sum() / 60),
          mean_seconds=("duration_seconds_num", "mean"),
          max_seconds=("duration_seconds_num", "max"),
      )
      .reset_index()
)

print(summary.to_string(index=False))
PY
