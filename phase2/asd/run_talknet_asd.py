"""Run official TalkNet-ASD inference on turn clips and write project manifests.

TalkNet's upstream demo performs S3FD face detection, IOU tracking, face-crop
creation, and audio-visual inference. This adapter preserves its scores in a
project-friendly row CSV and a per-frame/per-track CSV. It is deliberately
separate from the interpretable baseline ASD implementation.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def resolve_path(raw: object) -> Path:
    path = Path(str(raw or "").strip())
    if path.exists():
        return path
    if "data" in path.parts:
        candidate = ROOT / Path(*path.parts[path.parts.index("data") :])
        if candidate.exists():
            return candidate
    candidate = ROOT / path
    return candidate if candidate.exists() else path


def number(value: object, default: float = 0.0) -> float:
    value = pd.to_numeric(value, errors="coerce")
    return float(value) if pd.notna(value) else default


def run_demo(args: argparse.Namespace, video_path: Path, work_root: Path, sample_id: str) -> tuple[Path, Path]:
    sample_root = work_root / sample_id
    save_root = sample_root / "sample"
    if save_root.exists() and not args.skip_existing:
        shutil.rmtree(save_root)
    sample_root.mkdir(parents=True, exist_ok=True)
    input_link = sample_root / "sample.mp4"
    if input_link.exists() or input_link.is_symlink():
        input_link.unlink()
    input_link.symlink_to(video_path)
    command = [
        str(args.talknet_python),
        str(args.talknet_root / "demoTalkNet.py"),
        "--videoName", "sample",
        "--videoFolder", str(sample_root),
        "--pretrainModel", str(args.model),
        "--nDataLoaderThread", str(args.threads),
        "--facedetScale", str(args.facedet_scale),
        "--minTrack", str(args.min_track),
        "--numFailedDet", str(args.num_failed_det),
        "--minFaceSize", str(args.min_face_size),
        "--cropScale", str(args.crop_scale),
    ]
    log_path = sample_root / "talknet.log"
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=args.talknet_root, stdout=log, stderr=subprocess.STDOUT)
    if completed.returncode != 0:
        raise RuntimeError(f"TalkNet failed for {sample_id}; see {log_path}")
    work = save_root / "pywork"
    tracks = work / "tracks.pckl"
    scores = work / "scores.pckl"
    if not tracks.exists() or not scores.exists():
        raise RuntimeError(f"TalkNet did not produce tracks/scores for {sample_id}; see {log_path}")
    return tracks, scores


def extract_tracks(sample_id: str, tracks_path: Path, scores_path: Path, threshold: float) -> tuple[dict, list[dict]]:
    with tracks_path.open("rb") as handle:
        tracks = pickle.load(handle)
    with scores_path.open("rb") as handle:
        scores = pickle.load(handle)
    best_index = -1
    best_mean = -1.0
    best_ratio = 0.0
    frame_rows = []
    for index, (track, score_values) in enumerate(zip(tracks, scores)):
        logits = np.asarray(score_values, dtype=float).reshape(-1)
        # The upstream lossAV returns the speaking-class logit when labels are
        # omitted. Convert it to a probability before applying project gates.
        scores_array = 1.0 / (1.0 + np.exp(-np.clip(logits, -60.0, 60.0)))
        mean_score = float(scores_array.mean()) if scores_array.size else 0.0
        ratio = float(np.mean(scores_array >= threshold)) if scores_array.size else 0.0
        if mean_score > best_mean:
            best_index, best_mean, best_ratio = index, mean_score, ratio
        frame_numbers = np.asarray(track["track"]["frame"], dtype=int).reshape(-1)
        proc = track.get("proc_track", {})
        xs = np.asarray(proc.get("x", []), dtype=float).reshape(-1)
        ys = np.asarray(proc.get("y", []), dtype=float).reshape(-1)
        sizes = np.asarray(proc.get("s", []), dtype=float).reshape(-1)
        for position, frame_number in enumerate(frame_numbers):
            score = float(scores_array[min(position, len(scores_array) - 1)]) if len(scores_array) else 0.0
            frame_rows.append({
                "utterance_id": sample_id,
                "face_track_id": f"FACE_{index:03d}",
                "frame_number": int(frame_number),
                "frame_time_seconds": f"{float(frame_number) / 25.0:.3f}",
                "talknet_score": f"{score:.6f}",
                "track_x": f"{xs[position]:.3f}" if position < len(xs) else "",
                "track_y": f"{ys[position]:.3f}" if position < len(ys) else "",
                "track_half_size": f"{sizes[position]:.3f}" if position < len(sizes) else "",
            })
    row = {
        "talknet_face_track_count": str(len(tracks)),
        "talknet_best_face_track_id": f"FACE_{best_index:03d}" if best_index >= 0 else "",
        "talknet_active_speaker_detected": "YES" if best_index >= 0 and best_mean >= threshold else "NO",
        "talknet_active_speaker_score": f"{max(0.0, best_mean):.6f}",
        "talknet_active_speaker_frame_ratio": f"{best_ratio:.6f}",
        # Canonical fields allow the existing review/finalization tools to
        # consume TalkNet output without confusing it with the old baseline.
        "face_detected": "YES" if tracks else "NO",
        "active_speaker_detected": "YES" if best_index >= 0 and best_mean >= threshold else "NO",
        "active_speaker_confidence": f"{max(0.0, best_mean):.6f}",
        "active_speaker_frame_ratio": f"{best_ratio:.6f}",
        "talknet_status": "OK",
        "talknet_model": "TaoRuijie/TalkNet-ASD pretrained TalkSet model",
    }
    return row, frame_rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-csv", required=True)
    p.add_argument("--output-csv", required=True)
    p.add_argument("--tracks-csv", required=True)
    p.add_argument("--summary-json", required=True)
    p.add_argument("--talknet-root", required=True, type=Path)
    p.add_argument("--talknet-python", required=True, type=Path)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--work-root", required=True, type=Path)
    p.add_argument("--max-rows", type=int, default=0)
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--score-threshold", type=float, default=0.50, help="Speaking probability threshold after sigmoid conversion")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--facedet-scale", type=float, default=0.25)
    p.add_argument("--min-track", type=int, default=10)
    p.add_argument("--num-failed-det", type=int, default=10)
    p.add_argument("--min-face-size", type=int, default=1)
    p.add_argument("--crop-scale", type=float, default=0.40)
    args = p.parse_args()

    if not args.talknet_root.joinpath("demoTalkNet.py").exists():
        raise SystemExit(f"TalkNet checkout is missing demoTalkNet.py: {args.talknet_root}")
    if not args.talknet_python.exists():
        raise SystemExit(f"TalkNet Python does not exist: {args.talknet_python}")
    if not args.model.exists():
        raise SystemExit("TalkNet model is missing. Run setup or one demo first to download it.")

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if args.max_rows > 0:
        df = df.head(args.max_rows).copy()
    args.work_root.mkdir(parents=True, exist_ok=True)
    output_path, tracks_path, summary_path = map(Path, (args.output_csv, args.tracks_csv, args.summary_json))
    existing = pd.read_csv(output_path, dtype=str).fillna("") if args.skip_existing and output_path.exists() else pd.DataFrame()
    existing_by_id = existing.set_index("utterance_id").to_dict("index") if "utterance_id" in existing.columns else {}
    rows, frame_rows, created, reused, failed = [], [], 0, 0, []
    for _, source_row in df.iterrows():
        sample_id = str(source_row.get("utterance_id", "")).strip()
        if not sample_id:
            continue
        if sample_id in existing_by_id:
            rows.append(existing_by_id[sample_id])
            reused += 1
            continue
        video_path = resolve_path(source_row.get("clip_video_path") or source_row.get("video_path"))
        enriched = source_row.to_dict()
        try:
            if not video_path.exists():
                raise FileNotFoundError(video_path)
            tracks_p, scores_p = run_demo(args, video_path, args.work_root, sample_id)
            result, per_frame = extract_tracks(sample_id, tracks_p, scores_p, args.score_threshold)
            enriched.update(result)
            frame_rows.extend(per_frame)
            created += 1
        except Exception as exc:
            enriched.update({
                "talknet_face_track_count": "",
                "talknet_best_face_track_id": "",
                "talknet_active_speaker_detected": "UNKNOWN",
                "talknet_active_speaker_score": "",
                "talknet_active_speaker_frame_ratio": "",
                "face_detected": "UNKNOWN",
                "active_speaker_detected": "UNKNOWN",
                "active_speaker_confidence": "",
                "active_speaker_frame_ratio": "",
                "talknet_status": f"FAILED:{exc}",
                "talknet_model": "TaoRuijie/TalkNet-ASD pretrained TalkSet model",
            })
            failed.append({"utterance_id": sample_id, "error": str(exc)})
        rows.append(enriched)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tracks_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    pd.DataFrame(frame_rows).to_csv(tracks_path, index=False)
    summary = {
        "input_csv": str(args.input_csv),
        "output_csv": str(output_path),
        "tracks_csv": str(tracks_path),
        "work_root": str(args.work_root),
        "rows_processed": len(rows),
        "rows_created": created,
        "rows_reused": reused,
        "rows_failed": len(failed),
        "failed_rows": failed,
        "talknet_model": "TaoRuijie/TalkNet-ASD pretrained TalkSet model",
        "score_threshold": args.score_threshold,
        "notes": [
            "TalkNet is an audio-visual active-speaker model; it is not an emotion model.",
            "The output identifies a face track that is synchronized with speech, not the legal role of that person.",
            "A TalkNet YES does not prove that the face is the witness; speaker-face identity remains a human gate.",
            "Scores and tracks are preserved for calibration and visual audit.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
