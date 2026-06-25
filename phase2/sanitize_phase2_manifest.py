from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.dataset_builder import extract_audio
else:
    from .dataset_builder import extract_audio


EMOTION_MAP = {
    "neutral": 0,
    "fear": 1,
    "anger": 2,
    "sadness": 3,
    "stress": 4,
    "confidence": 5,
    "uncertain": 6,
}

HTML_RE = re.compile(r"^(?:<!doctype html>|<html\b|<head\b|<body\b|</?title\b|</?meta\b|</?script\b)", re.I)


def clean_text(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    if HTML_RE.match(text):
        return ""
    return text


def normalize_label(row: pd.Series) -> tuple[int, str]:
    raw = row.get("label", "")
    if pd.isna(raw) or str(raw).strip() == "":
        raw = row.get("emotion_label", "")
    text = str(raw).strip().lower()
    if text.isdigit():
        value = int(text)
        return value, text
    try:
        return int(float(text)), text
    except Exception:
        mapped = EMOTION_MAP.get(text)
        if mapped is None:
            raise ValueError(f"Unsupported label value: {raw}")
        return mapped, text


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanitize the Phase 2 legal-testimony manifest for training")
    parser.add_argument("--input-csv", type=str, required=True, help="Split manifest to sanitize")
    parser.add_argument("--output-csv", type=str, required=True, help="Cleaned trainer-ready CSV")
    parser.add_argument(
        "--audio-output-dir",
        type=str,
        default="data/processed/phase2/sanitized_audio",
        help="Where to store audio extracted from video when audio is missing",
    )
    parser.add_argument(
        "--use-cuda",
        action="store_true",
        help="Try CUDA-assisted ffmpeg decoding before falling back to CPU",
    )
    parser.add_argument(
        "--extract-audio-from-video",
        action="store_true",
        help="Extract audio from video files when audio_path is missing or invalid",
    )
    parser.add_argument("--require-video", action="store_true", help="Drop rows without a valid video file")
    parser.add_argument("--require-audio", action="store_true", help="Drop rows without a valid audio file")
    parser.add_argument("--min-text-length", type=int, default=1, help="Minimum number of words required in transcript text")
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    output_csv = Path(args.output_csv)
    if not input_csv.exists():
        raise FileNotFoundError(f"Input manifest not found: {input_csv}")

    df = pd.read_csv(input_csv)
    if df.empty:
        raise ValueError("Input manifest is empty")

    audio_out_dir = Path(args.audio_output_dir)
    audio_out_dir.mkdir(parents=True, exist_ok=True)

    cleaned_rows: list[dict[str, object]] = []
    dropped_html = 0
    dropped_text = 0
    dropped_audio = 0
    dropped_video = 0
    extracted_audio = 0
    failed_extractions: list[dict[str, str]] = []

    for _, row in df.iterrows():
        utterance_id = clean_text(row.get("utterance_id") or row.get("sample_id") or row.get("manifest_id"))
        if not utterance_id:
            continue

        sample_id = clean_text(row.get("sample_id") or utterance_id or row.get("manifest_id"))
        manifest_id = clean_text(row.get("manifest_id") or sample_id)
        transcript = clean_text(row.get("transcript") or row.get("utterance_text") or row.get("text"))
        video_path = clean_text(row.get("video_path"))
        audio_path = clean_text(row.get("audio_path"))
        speaker_name = clean_text(row.get("speaker_name"))
        speaker_role = clean_text(row.get("speaker_role"))
        case_name = clean_text(row.get("case_name"))
        tribunal = clean_text(row.get("tribunal"))
        start_time = clean_text(row.get("start_time"))
        end_time = clean_text(row.get("end_time"))

        if not transcript:
            dropped_html += 1
            continue
        if len(transcript.split()) < args.min_text_length:
            dropped_text += 1
            continue

        label, label_text = normalize_label(row)
        emotion_label = clean_text(row.get("emotion_label") or label_text or "")
        credibility_label = clean_text(row.get("credibility_label"))
        question_type = clean_text(row.get("question_type"))
        split = clean_text(row.get("split")) or "train"

        video_ok = bool(video_path and Path(video_path).exists())
        audio_ok = bool(audio_path and Path(audio_path).exists())

        if not video_ok and args.require_video:
            dropped_video += 1
            continue

        if not audio_ok and args.extract_audio_from_video and video_ok:
            try:
                audio_path = str(extract_audio(video_path, output_dir=audio_out_dir, use_cuda=args.use_cuda))
                audio_ok = True
                extracted_audio += 1
            except Exception as exc:
                audio_ok = False
                if len(failed_extractions) < 5:
                    failed_extractions.append(
                        {
                            "manifest_id": manifest_id,
                            "video_path": video_path,
                            "error": str(exc),
                        }
                    )

        if not audio_ok and args.require_audio:
            dropped_audio += 1
            continue

        cleaned_rows.append(
            {
                "sample_id": sample_id or utterance_id,
                "utterance_id": utterance_id,
                "manifest_id": manifest_id,
                "tribunal": tribunal,
                "case_name": case_name,
                "speaker_role": speaker_role,
                "speaker_name": speaker_name,
                "transcript": transcript,
                "utterance_text": transcript,
                "start_time": start_time,
                "end_time": end_time,
                "video_path": video_path if video_ok else "",
                "audio_path": audio_path if audio_ok else "",
                "label": label,
                "emotion_label": emotion_label or label_text,
                "credibility_label": credibility_label,
                "question_type": question_type,
                "cross_examination_flag": int(str(speaker_role).lower() in {"prosecutor", "defense counsel"}),
                "split": split,
            }
        )

    out_df = pd.DataFrame(cleaned_rows)
    out_df.to_csv(output_csv, index=False)

    summary = {
        "input_rows": len(df),
        "output_rows": len(out_df),
        "dropped_html_rows": dropped_html,
        "dropped_short_text_rows": dropped_text,
        "dropped_missing_audio_rows": dropped_audio,
        "dropped_missing_video_rows": dropped_video,
        "extracted_audio_rows": extracted_audio,
        "output_csv": str(output_csv),
    }
    summary_path = output_csv.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if failed_extractions:
        print("Sample audio extraction failures:")
        for item in failed_extractions:
            print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
