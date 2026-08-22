from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import ensure_annotation_schema


QUEUE_COLUMNS = ["utterance_id", "case_id", "case_number", "hearing_id", "witness_id", "youtube_id", "video_clip_path", "clip_video_path", "audio_clip_path", "clip_audio_path", "utterance_text", "previous_question_text", "examination_phase", "speaker_role", "witness_speaking_status", "text_emotion_label", "text_emotion_confidence", "audio_valence", "audio_arousal", "audio_dominance", "video_emotion_candidate", "suggested_basic_emotion", "suggested_courtroom_affect", "suggested_response_stance", "annotation_priority_score", "annotation_priority_reason", "basic_emotion_annotation_status", "courtroom_affect_annotation_status", "manual_review_required"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a reviewer-friendly annotation queue")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--max-rows", type=int, default=0)
    args = parser.parse_args()
    df = ensure_annotation_schema(pd.read_csv(args.input_csv, dtype=str).fillna(""))
    for column in QUEUE_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    out = df[QUEUE_COLUMNS].copy()
    out["_priority"] = pd.to_numeric(out["annotation_priority_score"], errors="coerce").fillna(-1)
    out = out.sort_values("_priority", ascending=False).drop(columns=["_priority"])
    if args.max_rows > 0:
        out = out.head(args.max_rows)
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    print(f"Wrote {len(out)} annotation queue rows to {output}")


if __name__ == "__main__":
    main()
