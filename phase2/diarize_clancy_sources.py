from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd


def overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def to_seconds(value: str) -> float:
    h, m, s = value.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def row_times(row: dict[str, str]) -> tuple[float, float]:
    start = row.get("turn_start_time", "")
    end = row.get("turn_end_time", "")
    if start and end:
        return to_seconds(start), to_seconds(end)
    offset = float(row.get("source_offset_seconds") or 0)
    return max(0, to_seconds(row.get("start_time", "00:00:00.000")) - offset), max(0, to_seconds(row.get("end_time", "00:00:00.000")) - offset)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Hugging Face pyannote diarization once per Clancy source audio")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--segments-csv", required=True)
    parser.add_argument("--model", default="pyannote/speaker-diarization-3.1")
    parser.add_argument("--max-sources", type=int, default=0)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--min-speakers", type=int, default=0)
    parser.add_argument("--max-speakers", type=int, default=0)
    args = parser.parse_args()
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise SystemExit("Set HF_TOKEN after accepting the pyannote model terms on Hugging Face")
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise SystemExit("Install pyannote.audio in the inference environment before running diarization") from exc

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    source_col = "source_audio_path" if "source_audio_path" in df.columns else "audio_path"
    sources = [x for x in df[source_col].drop_duplicates().tolist() if x]
    if args.max_sources > 0:
        sources = sources[: args.max_sources]
    try:
        pipeline = Pipeline.from_pretrained(args.model, token=token)
    except TypeError as exc:
        if "unexpected keyword argument 'token'" not in str(exc):
            raise
        pipeline = Pipeline.from_pretrained(args.model, use_auth_token=token)
    if args.device != "cpu":
        import torch

        if args.device == "cuda" and not torch.cuda.is_available():
            raise SystemExit("CUDA requested but torch.cuda.is_available() is false")
        if args.device == "mps" and not torch.backends.mps.is_available():
            raise SystemExit("MPS requested but torch.backends.mps.is_available() is false")
        pipeline.to(torch.device(args.device))
    all_segments: list[dict[str, str]] = []
    for source in sources:
        path = Path(source)
        if not path.exists():
            print(f"Skipping missing source audio: {path}")
            continue
        diarization_kwargs = {}
        if args.min_speakers > 0:
            diarization_kwargs["min_speakers"] = args.min_speakers
        if args.max_speakers > 0:
            diarization_kwargs["max_speakers"] = args.max_speakers
        diarization = pipeline(str(path), **diarization_kwargs)
        for segment, _, label in diarization.itertracks(yield_label=True):
            all_segments.append({
                "source_audio_path": str(path),
                "speaker_cluster_id": str(label),
                "segment_start_seconds": f"{segment.start:.3f}",
                "segment_end_seconds": f"{segment.end:.3f}",
                "diarization_model": args.model,
            })

    segments_path = Path(args.segments_csv)
    segments_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_segments).to_csv(segments_path, index=False)
    segment_df = pd.DataFrame(all_segments)
    enriched: list[dict[str, str]] = []
    for _, raw in df.iterrows():
        row = {key: str(value) for key, value in raw.to_dict().items()}
        source = row.get(source_col, "")
        start, end = row_times(row)
        candidates = []
        for segment in all_segments:
            if segment["source_audio_path"] != source:
                continue
            score = overlap(start, end, float(segment["segment_start_seconds"]), float(segment["segment_end_seconds"]))
            if score > 0:
                candidates.append((score, segment))
        if candidates:
            score, best = max(candidates, key=lambda item: item[0])
            row["speaker_cluster_id"] = best["speaker_cluster_id"]
            row["speaker_cluster_overlap_seconds"] = f"{score:.3f}"
            row["speaker_cluster_source"] = args.model
        else:
            row["speaker_cluster_id"] = "UNKNOWN"
            row["speaker_cluster_overlap_seconds"] = "0.000"
            row["speaker_cluster_source"] = "unresolved"
        row.setdefault("speaker_role", "UNKNOWN")
        row.setdefault("speaker_role_source", "unresolved")
        row.setdefault("speaker_role_confidence", "LOW")
        enriched.append(row)
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(enriched).to_csv(output_path, index=False)
    print(f"Wrote {len(enriched)} diarization-enriched rows to {output_path}")
    print(f"Wrote {len(all_segments)} diarization segments to {segments_path}")


if __name__ == "__main__":
    main()
