"""Create a reproducible Clancy end-to-end demonstration notebook."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "implementation_docments/LegalMemoCMT_Phase2_Clancy_End_to_End_Demo.ipynb"

def cell(kind, source):
    value = {"cell_type": kind, "metadata": {}, "source": source.splitlines(True)}
    if kind == "code":
        value.update({"execution_count": None, "outputs": []})
    return value

cells = [
cell("markdown", """# LegalMemoCMT Phase 2: Lindsay Clancy End-to-End Demo

This notebook demonstrates the Clancy pipeline from public source URLs through witness selection and DeBERTa scope inference. It prints the command, artifact status, and a compact result at every stage.

The notebook is read-only by default. Set an individual `RUN_*` flag to `True` before intentionally running a stage. No credentials are stored here.
"""),
cell("code", """from pathlib import Path
import json, os, shlex, subprocess
import pandas as pd

ROOT = Path.cwd()
if ROOT.name != "LegalMemoCMT":
    ROOT = Path("/Users/rajeshpmu/Desktop/LegalMemoCMT")
os.chdir(ROOT)
PYTHON_BIN = str(ROOT / ".venv/bin/python")
DIARIZATION_PYTHON = str(ROOT / ".venv-diarization/bin/python")
AUDIO_SER_PYTHON = str(ROOT / ".venv-audio-ser/bin/python")
MAX_ROWS = 200

# Safe demonstration defaults. Expensive/network stages do not run unless enabled.
RUN_SOURCE_PROBE = RUN_DOWNLOAD = RUN_TURNS = RUN_CLIPS = False
RUN_DIARIZATION = RUN_ROLE_FILTER = RUN_VIT = RUN_PHASE1 = False
RUN_AUDIO_SER = RUN_SCOPE_REVIEW = RUN_AFFECT = RUN_GATE = RUN_DEBERTA = False

print("Repository:", ROOT)
print("Python:", PYTHON_BIN)
print("All stages read-only:", not any(v for k,v in globals().items() if k.startswith("RUN_") and v))
"""),
cell("code", """def run_stage(name, command, outputs=(), execute=False, env=None):
    print(f"\\n=== {name} ===")
    print("COMMAND:", " ".join(shlex.quote(str(x)) for x in command))
    for item in outputs:
        print("ARTIFACT:", item, "->", "EXISTS" if (ROOT/item).exists() else "MISSING")
    if not execute:
        print("ACTION: display only; set the related RUN_* flag to True to execute")
        return
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    print("ACTION: completed")

def show_csv(path, n=5, columns=None):
    path = Path(path)
    if not path.is_absolute(): path = ROOT/path
    if not path.exists(): print("MISSING:", path); return None
    df = pd.read_csv(path, dtype=str).fillna("")
    cols = [c for c in (columns or list(df.columns)[:12]) if c in df.columns]
    print(f"{path}: rows={len(df):,}, columns={len(df.columns):,}")
    print(df[cols].head(n).to_string(index=False))
    return df

def show_json(path):
    path = Path(path)
    if not path.is_absolute(): path = ROOT/path
    if not path.exists(): print("MISSING:", path); return None
    print(json.dumps(json.loads(path.read_text()), indent=2)[:6000])
"""),
cell("markdown", """## 1. Source probe, download, and verification

`data/clancy_urls.txt` is the curated public source list. The source-manifest command probes metadata; the corpus command downloads media and subtitles. `--skip-existing` prevents repeated downloads, while `--verify` checks local media. A successful download is not automatically a witness-training row.
"""),
cell("code", """run_stage("Source metadata probe", ["bash", "phase2/run_build_clancy_source_manifest.sh", "--skip-existing"], [Path("data/processed/phase2/clancy/clancy_source_manifest.csv")], RUN_SOURCE_PROBE)
show_csv("data/processed/phase2/clancy/clancy_source_manifest.csv", 5)

download_env = {**os.environ, "PYTHON_BIN": PYTHON_BIN, "YTDLP_BIN": str(ROOT/".venv/bin/yt-dlp"), "COOKIES_FROM_BROWSER": ""}
run_stage("Download and verify source corpus", ["bash", "phase2/run_build_clancy_corpus.sh", "--skip-existing", "--verify"], [Path("data/processed/phase2/clancy/clancy_corpus_manifest.csv")], RUN_DOWNLOAD, download_env)
show_csv("data/processed/phase2/clancy/clancy_corpus_manifest.csv", 5)
show_json("reports/phase2/clancy_corpus_summary.json")
"""),
cell("markdown", """## 2. Build turns and true turn-level MP4/WAV clips

Subtitle cues are grouped into turn rows. The clip builder applies source offsets and exports matching video/audio paths. The raw MP4 remains the provenance source.
"""),
cell("code", """run_stage("Build turn manifest", ["bash", "phase2/run_build_clancy_turn_manifest.sh", "--skip-existing"], [Path("data/processed/phase2/clancy/clancy_turn_manifest.csv")], RUN_TURNS)
show_csv("data/processed/phase2/clancy/clancy_turn_manifest.csv", 5, ["turn_id", "youtube_id", "turn_text", "turn_start_time", "turn_end_time", "turn_duration_seconds"])
run_stage("Create turn MP4 and WAV clips", ["bash", "phase2/run_build_clancy_turn_clips.sh", "--skip-existing"], [Path("data/processed/phase2/clancy/clancy_turn_manifest_clipped.csv")], RUN_CLIPS)
show_csv("data/processed/phase2/clancy/clancy_turn_manifest_clipped.csv", 5, ["turn_id", "youtube_id", "clip_video_path", "clip_audio_path", "clip_start_seconds", "clip_end_seconds", "clip_status"])
"""),
cell("markdown", """## 3. Diarization, role mapping, and witness-only selection

Pyannote creates source-local anonymous clusters. It does not identify legal roles, so the manually reviewed cluster-role map is applied afterward. The witness filter then creates usable and review views.
"""),
cell("code", """diarized = "data/processed/phase2/clancy/clancy_turn_manifest_clipped_diarized.csv"
segments = "data/processed/phase2/clancy/clancy_diarization_segments_all.csv"
run_stage("Parallel Pyannote diarization", ["bash", "phase2/run_clancy_diarization_parallel.sh", "--input-csv", "data/processed/phase2/clancy/clancy_turn_manifest_clipped.csv", "--output-csv", diarized, "--segments-csv", segments, "--device", "cpu", "--workers", "3"], [Path(diarized), Path(segments)], RUN_DIARIZATION, {**os.environ, "PYTHON_BIN": DIARIZATION_PYTHON})
show_csv(segments, 5, ["youtube_id", "speaker_cluster_id", "segment_start", "segment_end", "segment_duration_seconds"])

role_mapped = "data/processed/phase2/clancy/clancy_turn_manifest_clipped_role_mapped_v10.csv"
role_map = "data/processed/phase2/clancy/clancy_speaker_role_map_v10.csv"
run_stage("Apply reviewed cluster roles", [PYTHON_BIN, "phase2/apply_clancy_cluster_role_map.py", "--input-csv", diarized, "--mapping-csv", role_map, "--output-csv", role_mapped], [Path(role_mapped), Path(role_map)], RUN_ROLE_FILTER)
show_csv(role_mapped, 5, ["turn_id", "youtube_id", "speaker_cluster_id", "speaker_role", "speaker_role_source", "speaker_role_confidence"])

usable = "data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_usable.csv"
run_stage("Build witness-only files", ["bash", "phase2/run_filter_legalmeld_rows_by_witness_role.sh", "--input-csv", role_mapped, "--output-dir", "data/processed/phase2/clancy/witness_only_v10", "--base-name", "clancy_witness_speaking", "--discovery-csv", "/dev/null"], [Path(usable), Path("data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_review.csv")], RUN_ROLE_FILTER)
show_csv(usable, 5, ["utterance_id", "youtube_id", "speaker_role", "witness_speaking_status", "clip_video_path", "clip_audio_path"])
show_csv("data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_visual_verified.csv", 5, ["utterance_id", "speaker_role", "witness_speaking_status", "visual_verification_status", "visual_speaker_match"])
"""),
cell("markdown", """## 4. ViT features and Phase 1 basic-emotion evidence

ViT creates 768-dimensional `.npy` video features. The Phase 1 trimodal checkpoint supplies the original seven-class MELD-compatible prediction. Both outputs remain machine evidence.
"""),
cell("code", """vit_out = "data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_visual_verified_vit_200.csv"
vit_env = {**os.environ, "PYTHON_BIN": "/opt/anaconda3/bin/python", "INPUT_CSV": str(ROOT/"data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_visual_verified.csv"), "OUTPUT_CSV": str(ROOT/vit_out), "OUTPUT_ROOT": str(ROOT/"data/processed/phase2/clancy/vit_facecrop_embeddings"), "SUMMARY_JSON": str(ROOT/"reports/phase2/clancy_vit_facecrop_200.json")}
run_stage("Extract ViT face-crop embeddings", ["bash", "phase2/run_build_clancy_vit_facecrop_embeddings.sh", "--max-rows", str(MAX_ROWS), "--batch-size", "8", "--device", "cpu"], [Path(vit_out)], RUN_VIT, vit_env)
show_json("reports/phase2/clancy_vit_facecrop_200.json")

phase1_out = "data/processed/phase2/clancy/phase1_trimodal_pseudo_labels_200.csv"
phase1_env = {**os.environ, "PYTHON_BIN": PYTHON_BIN, "INPUT_CSV": str(ROOT/vit_out), "OUTPUT_CSV": str(ROOT/phase1_out), "CHECKPOINT": str(ROOT/"results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt"), "SUMMARY_JSON": str(ROOT/"reports/phase2/clancy_phase1_trimodal_pseudo_labels_200.json"), "MAX_ROWS": str(MAX_ROWS), "BATCH_SIZE": "4", "MODALITIES": "text,audio,video"}
run_stage("Phase 1 trimodal pseudo-label pilot", ["bash", "phase2/run_pseudo_label_clancy_with_phase1.sh"], [Path(phase1_out)], RUN_PHASE1, phase1_env)
show_csv(phase1_out, 5, ["utterance_id", "phase1_basic_emotion", "phase1_basic_emotion_confidence", "video_features_path"])
show_json("reports/phase2/clancy_phase1_trimodal_pseudo_labels_200.json")
"""),
cell("markdown", """## 5. Audio-SER, scope-aware review, affect candidates, and gate

The final pilot stages preserve independent evidence: audio-SER, transcript scope, courtroom-affect candidates, and acceptance status. DeBERTa is the final planned enhancement and writes additional scope suggestions; it does not overwrite existing labels.
"""),
cell("code", """audio_out = "data/processed/phase2/clancy/audio_ser_evidence_200.csv"
run_stage("Audio-SER evidence", ["bash", "phase2/annotation/run_audio_ser_evidence.sh", "--input-csv", phase1_out, "--output-csv", audio_out, "--summary-json", "reports/phase2/clancy_audio_ser_evidence_200.json", "--max-rows", str(MAX_ROWS)], [Path(audio_out)], RUN_AUDIO_SER, {**os.environ, "PYTHON_BIN": AUDIO_SER_PYTHON})
show_csv(audio_out, 3, ["utterance_id", "audio_emotion_candidate", "audio_emotion_confidence", "audio_valence", "audio_excitement", "audio_dominance"])

scope_out = "data/processed/phase2/clancy/emotion_scope_review_200_scope_aware.csv"
run_stage("Scope-aware review", [PYTHON_BIN, "phase2/annotation/build_clancy_emotion_scope_review.py", "--phase1-csv", phase1_out, "--audio-ser-csv", audio_out, "--output-csv", scope_out, "--summary-json", "reports/phase2/clancy_emotion_scope_review_200_scope_aware.json", "--max-rows", str(MAX_ROWS), "--policy", "scope_aware"], [Path(scope_out)], RUN_SCOPE_REVIEW)
show_csv(scope_out, 3, ["utterance_id", "phase1_basic_emotion", "audio_emotion_candidate", "emotion_target_scope", "basic_emotion_review_candidate"])

affect_out = "data/processed/phase2/clancy/courtroom_affect_candidates_200_v4.csv"
run_stage("Courtroom-affect candidates", [PYTHON_BIN, "phase2/annotation/propose_clancy_courtroom_affect.py", "--input-csv", scope_out, "--output-csv", affect_out, "--summary-json", "reports/phase2/clancy_courtroom_affect_candidates_200_v4.json", "--max-rows", str(MAX_ROWS)], [Path(affect_out)], RUN_AFFECT)
show_csv(affect_out, 3, ["utterance_id", "proposed_basic_emotion", "proposed_courtroom_affect", "proposed_courtroom_affect_confidence", "negative_activation_candidate"])

gated = "data/processed/phase2/clancy/courtroom_affect_candidates_200_v4_gated.csv"
run_stage("Acceptance gate", [PYTHON_BIN, "phase2/annotation/apply_clancy_annotation_acceptance_gate.py", "--input-csv", affect_out, "--output-csv", gated, "--summary-json", "reports/phase2/clancy_courtroom_affect_candidates_200_v4_gated.json", "--basic-threshold", "0.70", "--affect-threshold", "0.60"], [Path(gated)], RUN_GATE)
show_csv(gated, 5, ["utterance_id", "final_basic_emotion", "final_courtroom_affect", "critical_conflict", "annotation_status", "annotation_tier"])
"""),
cell("markdown", """## 6. Planned DeBERTa scope inference

`MoritzLaurer/deberta-v3-large-zeroshot-v2.0` compares transcript context with natural-language hypotheses for target and temporal scope. Run it only after installing `transformers`. Its suggestions are evidence for review, not gold labels.
"""),
cell("code", """deberta_out = "data/processed/phase2/clancy/emotion_scope_review_200_deberta.csv"
run_stage("DeBERTa target/temporal scope inference", [PYTHON_BIN, "phase2/annotation/run_deberta_scope_inference.py", "--input-csv", scope_out, "--output-csv", deberta_out, "--summary-json", "reports/phase2/clancy_emotion_scope_review_200_deberta.json", "--max-rows", str(MAX_ROWS), "--device", "-1"], [Path(deberta_out)], RUN_DEBERTA)
show_csv(deberta_out, 5, ["utterance_id", "emotion_target_scope", "deberta_target_scope", "deberta_target_confidence", "deberta_temporal_scope"])
show_json("reports/phase2/clancy_emotion_scope_review_200_deberta.json")
"""),
cell("markdown", """## Final interpretation

The notebook demonstrates an auditable evidence chain. The first 200 rows are a controlled pilot selected from the witness-visible speaking pool. They validate feature paths, model outputs, scope rules, affect candidates, and the acceptance gate. The final Clancy corpus must be regenerated from the complete eligible pool after pilot review; its final rows and minutes must be measured after all quality gates, not extrapolated from 200 rows.
"""),
]

OUT.write_text(json.dumps({"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}, indent=1))
print(OUT)

if __name__ == "__main__":
    pass
