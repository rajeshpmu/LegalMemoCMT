"""Diarize Tupac source audio with Pyannote 4-compatible output handling."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd


def overlap(a: float, b: float, c: float, d: float) -> float:
    return max(0.0, min(b, d) - max(a, c))


def seconds(value: str) -> float:
    h, m, s = value.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def extract_tracks(result):
    annotation = getattr(result, "speaker_diarization", None)
    if annotation is None:
        annotation = getattr(result, "diarization", None)
    if annotation is None:
        annotation = result
    if not hasattr(annotation, "itertracks"):
        raise TypeError(f"Unsupported Pyannote output type: {type(result).__name__}")
    return annotation.itertracks(yield_label=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--segments-csv", required=True)
    parser.add_argument("--model", default="pyannote/speaker-diarization-3.1")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--skip-completed", action="store_true")
    parser.add_argument("--min-speakers", type=int, default=0)
    parser.add_argument("--max-speakers", type=int, default=0)
    args = parser.parse_args()

    from pyannote.audio import Pipeline
    import torch

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    source_col = "source_audio_path" if "source_audio_path" in df.columns else "audio_path"
    sources = list(dict.fromkeys(x for x in df[source_col].tolist() if x))
    segment_path = Path(args.segments_csv)
    existing = pd.read_csv(segment_path, dtype=str).fillna("").to_dict("records") if args.skip_completed and segment_path.exists() else []
    completed = {row.get("source_audio_path", "") for row in existing if row.get("source_audio_path")}
    pending = [source for source in sources if source not in completed]
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if pending and not token:
        raise SystemExit("Set HF_TOKEN")
    pipeline = Pipeline.from_pretrained(args.model, token=token) if pending else None
    if pipeline is not None and args.device != "cpu":
        pipeline.to(torch.device(args.device))

    segments = list(existing)
    for source in pending:
        path = Path(source)
        if not path.exists():
            print(f"Skipping missing source audio: {path}")
            continue
        kwargs = {}
        if args.min_speakers > 0:
            kwargs["min_speakers"] = args.min_speakers
        if args.max_speakers > 0:
            kwargs["max_speakers"] = args.max_speakers
        result = pipeline(str(path), **kwargs)
        for turn, _, label in extract_tracks(result):
            segments.append({
                "source_audio_path": str(path),
                "speaker_cluster_id": str(label),
                "segment_start_seconds": f"{turn.start:.3f}",
                "segment_end_seconds": f"{turn.end:.3f}",
                "diarization_model": args.model,
            })

    segment_path.parent.mkdir(parents=True, exist_ok=True)
    segment_df = pd.DataFrame(segments, columns=["source_audio_path", "speaker_cluster_id", "segment_start_seconds", "segment_end_seconds", "diarization_model"])
    segment_df.drop_duplicates(subset=["source_audio_path", "speaker_cluster_id", "segment_start_seconds", "segment_end_seconds"], inplace=True)
    segment_df.to_csv(segment_path, index=False)

    enriched = []
    for _, raw in df.iterrows():
        row = raw.to_dict()
        source = row.get(source_col, "")
        start_key = "turn_start_time" if row.get("turn_start_time") else "start_time"
        end_key = "turn_end_time" if row.get("turn_end_time") else "end_time"
        start, end = seconds(row[start_key]), seconds(row[end_key])
        matches = [s for s in segments if s["source_audio_path"] == source and overlap(start, end, float(s["segment_start_seconds"]), float(s["segment_end_seconds"])) > 0]
        if matches:
            best = max(matches, key=lambda s: overlap(start, end, float(s["segment_start_seconds"]), float(s["segment_end_seconds"])))
            row["speaker_cluster_id"] = best["speaker_cluster_id"]
            row["speaker_cluster_overlap_seconds"] = f"{overlap(start, end, float(best['segment_start_seconds']), float(best['segment_end_seconds'])):.3f}"
            row["speaker_cluster_source"] = args.model
        else:
            row["speaker_cluster_id"] = "UNKNOWN"
            row["speaker_cluster_overlap_seconds"] = "0.000"
            row["speaker_cluster_source"] = "unresolved"
        row.setdefault("speaker_role", "UNKNOWN")
        row.setdefault("speaker_role_source", "unresolved")
        row.setdefault("speaker_role_confidence", "LOW")
        enriched.append(row)
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(enriched).to_csv(output, index=False)
    print(f"Wrote {len(enriched)} rows and {len(segment_df)} segments using Pyannote 4 output handling")
