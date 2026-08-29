from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ANNOTATION_STATUSES = {"UNLABELED", "AUTO_SUGGESTED", "PSEUDO_LABELED", "HUMAN_SINGLE", "HUMAN_MULTI", "ADJUDICATED", "REJECTED"}
BASIC_EMOTIONS = ["neutral", "anger", "disgust", "fear", "joy", "sadness", "surprise"]
COURTROOM_AFFECT = ["CALM_COMPOSED", "HESITANT_UNCERTAIN", "GUARDED", "DEFENSIVE", "ASSERTIVE", "TENSE", "DISTRESSED", "AGITATED", "UNCLEAR"]

CANONICAL_DEFAULTS = {
    "basic_emotion": "", "basic_emotion_source": "", "basic_emotion_confidence": "", "basic_emotion_annotation_status": "UNLABELED",
    "courtroom_affect": "", "courtroom_affect_confidence": "", "courtroom_affect_annotation_status": "UNLABELED", "affect_intensity": "", "valence": "", "arousal": "",
    "examination_phase": "UNKNOWN", "question_type": "UNKNOWN", "challenge_level": "UNKNOWN", "response_stance": "UNKNOWN", "previous_question_text": "", "annotation_context_start": "", "annotation_context_end": "",
    "cue_hesitation": "", "cue_long_pause": "", "cue_self_correction": "", "cue_repetition": "", "cue_interruption": "", "cue_overlap": "", "cue_voice_rise": "", "cue_voice_drop": "", "cue_speech_rate_change": "", "cue_visible_distress": "", "cue_gaze_shift": "", "cue_head_movement": "", "cue_facial_tension": "",
    "response_latency_ms": "", "mean_pause_ms": "", "speech_rate_wpm": "", "overlap_duration_ms": "",
}

SUGGESTION_DEFAULTS = {
    "suggested_basic_emotion": "", "suggested_basic_emotion_confidence": "", "suggested_courtroom_affect": "", "suggested_courtroom_affect_confidence": "", "suggested_response_stance": "", "suggested_response_stance_confidence": "",
    "text_emotion_label": "", "text_emotion_confidence": "", "text_emotion_model": "", "text_affect_candidate": "", "text_affect_confidence": "",
    "audio_valence": "", "audio_arousal": "", "audio_excitement": "", "audio_dominance": "", "audio_affect_model": "", "audio_emotion_candidate": "", "audio_emotion_confidence": "",
    "video_emotion_candidate": "", "video_emotion_confidence": "", "video_affect_candidate": "", "video_affect_confidence": "", "video_model": "",
    "prediction_entropy": "", "prediction_margin": "", "modality_disagreement_score": "", "class_rarity_score": "", "annotation_priority_score": "", "annotation_priority_reason": "",
    "pseudo_label": "", "pseudo_label_confidence": "", "pseudo_label_model": "", "pseudo_label_model_checkpoint": "", "pseudo_label_iteration": "", "pseudo_label_acceptance_reason": "",
    "annotation_iteration": "0", "training_iteration": "0", "model_checkpoint": "", "selection_strategy": "", "selection_score": "", "review_timestamp": "", "label_changed_after_review": "",
}


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open() as handle:
        return yaml.safe_load(handle) or {}


def ensure_annotation_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column, default in {**CANONICAL_DEFAULTS, **SUGGESTION_DEFAULTS}.items():
        if column not in out.columns:
            out[column] = default
    if "emotion_label" in out.columns:
        compatible = out["emotion_label"].where(out["emotion_label"].isin(BASIC_EMOTIONS), "")
        out["basic_emotion"] = out["basic_emotion"].where(out["basic_emotion"].isin(BASIC_EMOTIONS), compatible)
    if "emotion_label_source" in out.columns:
        out["basic_emotion_source"] = out["basic_emotion_source"].where(out["basic_emotion_source"].ne(""), out["emotion_label_source"])
    if "emotion_label_confidence" in out.columns:
        out["basic_emotion_confidence"] = out["basic_emotion_confidence"].where(out["basic_emotion_confidence"].ne(""), out["emotion_label_confidence"])
    return out


def write_json(path: str | Path, value: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
