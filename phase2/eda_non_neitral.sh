cd /workspace/LegalMemoCMT

./.venv/bin/python - <<'PY'
import pandas as pd

p = "data/processed/phase2/clancy/human_scope_suggestions_full_neutral_gated_relaxed_v1.csv"
df = pd.read_csv(p, dtype=str).fillna("")

non_neutral = df[
    df["phase1_basic_emotion"].str.lower().ne("neutral")
].copy()

numeric = [
    "phase1_basic_emotion_confidence",
    "audio_emotion_confidence",
    "audio_valence",
    "audio_excitement",
    "audio_arousal",
    "audio_dominance",
    "machine_proposed_basic_emotion_confidence",
    "proposed_basic_emotion_confidence",
    "proposed_courtroom_affect_confidence",
    "proposed_affect_intensity",
    "clip_duration_seconds",
]

for col in numeric:
    if col in non_neutral:
        non_neutral[col] = pd.to_numeric(non_neutral[col], errors="coerce")

print("=== Non-neutral Phase 1 rows ===")
print("Rows:", len(non_neutral))
print("Unique utterances:", non_neutral["utterance_id"].nunique())

print("\n=== Phase 1 emotion distribution ===")
print(non_neutral["phase1_basic_emotion"].value_counts().to_string())

print("\n=== Numeric evidence summary ===")
available_numeric = [c for c in numeric if c in non_neutral.columns]
print(non_neutral[available_numeric].describe().T.to_string())

print("\n=== Phase 1 emotion by machine status ===")
print(pd.crosstab(
    non_neutral["phase1_basic_emotion"],
    non_neutral["machine_annotation_status"],
    margins=True
).to_string())

print("\n=== Phase 1 emotion by audio-SER candidate ===")
if "audio_emotion_candidate" in non_neutral:
    print(pd.crosstab(
        non_neutral["phase1_basic_emotion"],
        non_neutral["audio_emotion_candidate"],
        margins=True
    ).to_string())

print("\n=== Phase 1 emotion by modality disagreement ===")
if "modality_disagreement_score" in non_neutral:
    print(pd.crosstab(
        non_neutral["phase1_basic_emotion"],
        non_neutral["modality_disagreement_score"],
        margins=True
    ).to_string())

print("\n=== Phase 1 emotion by semantic leakage risk ===")
if "semantic_leakage_risk" in non_neutral:
    print(pd.crosstab(
        non_neutral["phase1_basic_emotion"],
        non_neutral["semantic_leakage_risk"],
        margins=True
    ).to_string())

print("\n=== Odyssey evidence status ===")
for col in ["audio_ser_odyssey_status", "audio_affect_model"]:
    if col in non_neutral:
        print(f"\n{col}")
        print(non_neutral[col].value_counts(dropna=False).to_string())

print("\n=== Candidate rows for threshold analysis ===")
cols = [
    "utterance_id",
    "utterance_text",
    "phase1_basic_emotion",
    "phase1_basic_emotion_confidence",
    "audio_emotion_candidate",
    "audio_emotion_confidence",
    "audio_valence",
    "audio_excitement",
    "audio_dominance",
    "modality_disagreement_score",
    "semantic_leakage_risk",
    "emotion_target_scope",
    "deberta_target_scope",
    "machine_proposed_basic_emotion",
    "machine_proposed_basic_emotion_confidence",
    "proposed_courtroom_affect",
    "proposed_courtroom_affect_confidence",
    "machine_annotation_status",
]
available_cols = [c for c in cols if c in non_neutral.columns]
print(non_neutral[available_cols].to_string(index=False))

out = "data/processed/phase2/clancy/non_neutral_phase1_evidence_comparison.csv"
non_neutral.to_csv(out, index=False)
print("\nWrote:", out)
PY
