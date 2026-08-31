cd /workspace/LegalMemoCMT

./.venv/bin/python - <<'PY'
import pandas as pd

p = "data/processed/phase2/clancy/human_scope_suggestions_full_neutral_gated_relaxed_v1.csv"
df = pd.read_csv(p, dtype=str).fillna("")

df["duration_seconds_num"] = pd.to_numeric(
    df.get("clip_duration_seconds", 0), errors="coerce"
).fillna(0)

accepted = df[df["machine_annotation_status"] == "AUTO_ADJUDICATED"].copy()
unresolved = df[df["machine_annotation_status"] != "AUTO_ADJUDICATED"].copy()

print("=== Overall ===")
print("Total rows:", len(df))
print("Unique utterances:", df["utterance_id"].nunique())
print("Accepted machine candidates:", len(accepted))
print("Unresolved rows:", len(unresolved))
print("Accepted percentage:", round(100 * len(accepted) / len(df), 2))

print("\n=== machine_final_basic_emotion ===")
print(accepted["machine_final_basic_emotion"].value_counts(dropna=False).to_string())

print("\n=== Phase 1 emotion among accepted rows ===")
print(accepted["phase1_basic_emotion"].value_counts(dropna=False).to_string())

print("\n=== DeBERTa target among accepted rows ===")
print(accepted["deberta_target_scope"].value_counts(dropna=False).to_string())

print("\n=== Phase 1 confidence ===")
print(accepted["phase1_basic_emotion_confidence"].astype(float).describe().to_string())

print("\n=== DeBERTa confidence ===")
print(accepted["deberta_target_scope_confidence"].astype(float).describe().to_string())

print("\n=== Accepted duration ===")
print("Minutes:", round(accepted["duration_seconds_num"].sum() / 60, 3))
print("Hours:", round(accepted["duration_seconds_num"].sum() / 3600, 4))
print(accepted["duration_seconds_num"].describe().to_string())

print("\n=== Accepted rows by split ===")
if "split" in accepted:
    print(accepted["split"].value_counts().to_string())

print("\n=== Accepted rows by duration band ===")
accepted["duration_band"] = pd.cut(
    accepted["duration_seconds_num"],
    bins=[-float("inf"), 0.8, 20, 30, float("inf")],
    labels=["<0.8", "0.8-<20", "20-30", ">30"],
    right=False,
)
print(accepted["duration_band"].value_counts(sort=False).to_string())

print("\n=== Machine status by Phase 1 emotion ===")
print(pd.crosstab(df["phase1_basic_emotion"], df["machine_annotation_status"]).to_string())

print("\n=== Sample accepted rows ===")
cols = [
    "utterance_id",
    "utterance_text",
    "phase1_basic_emotion",
    "phase1_basic_emotion_confidence",
    "deberta_target_scope",
    "deberta_target_scope_confidence",
    "machine_final_basic_emotion",
    "machine_annotation_status",
    "auto_gate_reason",
]
print(accepted[[c for c in cols if c in accepted.columns]].head(20).to_string(index=False))
PY
