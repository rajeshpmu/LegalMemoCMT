from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common import ensure_annotation_schema

DEFAULT_TEXT_MODEL = "MoritzLaurer/deberta-v3-large-zeroshot-v2.0"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate optional non-canonical model suggestions")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--text-model", default=DEFAULT_TEXT_MODEL, help="Zero-shot NLI model")
    parser.add_argument("--audio-model", default="", help="Optional audio affect model")
    parser.add_argument("--max-rows", type=int, default=0)
    args = parser.parse_args()
    df = ensure_annotation_schema(pd.read_csv(args.input_csv, dtype=str).fillna(""))
    if args.max_rows > 0:
        df = df.head(args.max_rows).copy()
    text_pipe = None
    audio_pipe = None
    if args.text_model:
        from transformers import pipeline
        text_pipe = pipeline("zero-shot-classification", model=args.text_model)
    if args.audio_model:
        from transformers import pipeline
        audio_pipe = pipeline("audio-classification", model=args.audio_model, trust_remote_code=True)
    for index, row in df.iterrows():
        if text_pipe and row.get("utterance_text", ""):
            candidates = ["calm and composed", "hesitant and uncertain", "guarded and cautious", "defensive or resisting", "assertive and firm", "tense", "distressed", "agitated"]
            result = text_pipe(row["utterance_text"], candidates, multi_label=False)
            label = result["labels"][0]
            score = float(result["scores"][0])
            df.at[index, "text_affect_candidate"] = label
            df.at[index, "text_affect_confidence"] = f"{score:.6f}"
            df.at[index, "text_emotion_model"] = args.text_model
            df.at[index, "suggested_courtroom_affect"] = label.upper().replace(" AND ", "_").replace(" ", "_")
            df.at[index, "suggested_courtroom_affect_confidence"] = f"{score:.6f}"
        audio_path = row.get("clip_audio_path") or row.get("audio_clip_path") or row.get("audio_path")
        if audio_pipe and audio_path and Path(audio_path).exists():
            prediction = audio_pipe(audio_path, top_k=3)
            top = prediction[0] if prediction else {}
            df.at[index, "audio_emotion_candidate"] = str(top.get("label", ""))
            df.at[index, "audio_emotion_confidence"] = f"{float(top.get('score', 0.0)):.6f}"
            df.at[index, "audio_affect_model"] = args.audio_model
        if text_pipe or audio_pipe:
            df.at[index, "basic_emotion_annotation_status"] = "AUTO_SUGGESTED"
            df.at[index, "courtroom_affect_annotation_status"] = "AUTO_SUGGESTED"
    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(json.dumps({"rows_written": len(df), "text_model": args.text_model or None, "audio_model": args.audio_model or None, "canonical_labels_overwritten": False, "note": "Suggestions require review and do not replace human labels."}, indent=2))


if __name__ == "__main__":
    main()
