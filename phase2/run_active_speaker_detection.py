"""Run a conservative audio-visual active-speaker screening stage.

This is an interpretable baseline, not a TalkNet checkpoint. It combines
short-term audio energy with lower-face motion for each tracked face. It does
not identify the person's role; speaker-face identity remains UNKNOWN until
manual review or an identity-mapping stage confirms it.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def resolve_path(raw: str) -> Path:
    path = Path(str(raw or "").strip())
    if path.exists():
        return path
    parts = path.parts
    if "data" in parts:
        candidate = ROOT / Path(*parts[parts.index("data") :])
        if candidate.exists():
            return candidate
    candidate = ROOT / path
    return candidate if candidate.exists() else path


def numeric(row: pd.Series, *names: str, default: float = 0.0) -> float:
    for name in names:
        value = pd.to_numeric(row.get(name, ""), errors="coerce")
        if pd.notna(value):
            return float(value)
    return default


def robust_scale(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    lo, hi = np.percentile(values, [10, 90])
    if hi <= lo:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def audio_energy(audio_path: Path, frame_times: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    if not audio_path.exists() or frame_times.size == 0:
        return np.zeros(frame_times.shape, dtype=np.float32)
    try:
        import soundfile as sf

        samples, source_rate = sf.read(str(audio_path), dtype="float32", always_2d=True)
        signal = samples.mean(axis=1)
    except Exception:
        return np.zeros(frame_times.shape, dtype=np.float32)
    if source_rate != sample_rate:
        duration = len(signal) / float(source_rate)
        target_count = max(1, int(round(duration * sample_rate)))
        old_x = np.linspace(0.0, duration, len(signal), endpoint=False)
        new_x = np.linspace(0.0, duration, target_count, endpoint=False)
        signal = np.interp(new_x, old_x, signal).astype(np.float32)
    half = max(1, int(round(0.04 * sample_rate)))
    values = []
    for time_s in frame_times:
        center = int(round(float(time_s) * sample_rate))
        chunk = signal[max(0, center - half) : min(len(signal), center + half)]
        values.append(float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0)
    return robust_scale(np.asarray(values, dtype=np.float32))


def detect_faces(gray: np.ndarray, cascade: cv2.CascadeClassifier) -> list[tuple[int, int, int, int]]:
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(32, 32))
    return [tuple(map(int, face)) for face in faces]


def mouth_motion(previous: np.ndarray | None, gray: np.ndarray, face: tuple[int, int, int, int]) -> float:
    x, y, w, h = face
    # Lower face is a proxy for mouth motion; it is intentionally reported as
    # screening evidence, not as proof that a face is speaking.
    crop = gray[y + int(h * 0.48) : y + int(h * 0.95), x : x + w]
    if crop.size == 0 or previous is None or previous.shape != crop.shape:
        return 0.0
    return float(np.mean(cv2.absdiff(previous, crop)) / 255.0)


def assign_tracks(previous: dict[int, tuple[float, float]], faces: list[tuple[int, int, int, int]], next_id: int) -> tuple[dict[int, tuple[int, int, int, int]], int]:
    assigned: dict[int, tuple[int, int, int, int]] = {}
    unused = set(range(len(faces)))
    for track_id, (px, py) in previous.items():
        best = None
        best_distance = float("inf")
        for index in unused:
            x, y, w, h = faces[index]
            distance = math.hypot((x + w / 2) - px, (y + h / 2) - py)
            if distance < best_distance:
                best, best_distance = index, distance
        if best is not None and best_distance <= 0.75 * max(faces[best][2], faces[best][3]):
            assigned[track_id] = faces[best]
            unused.remove(best)
    for index in sorted(unused):
        assigned[next_id] = faces[index]
        next_id += 1
    return assigned, next_id


def process_row(row: pd.Series, cascade: cv2.CascadeClassifier, args: argparse.Namespace) -> tuple[dict[str, str], list[dict[str, str]]]:
    output = row.to_dict()
    video_raw = row.get("clip_video_path") or row.get("video_path") or row.get("source_video_path")
    audio_raw = row.get("clip_audio_path") or row.get("audio_path") or row.get("source_audio_path")
    video_path, audio_path = resolve_path(video_raw), resolve_path(audio_raw)
    capture = cv2.VideoCapture(str(video_path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else numeric(row, "clip_duration_seconds", "duration_seconds")
    times = np.linspace(0.0, max(0.0, duration - 1.0 / fps), max(1, args.samples))
    energies = audio_energy(audio_path, times)
    tracks: dict[int, list[float]] = {}
    previous_centers: dict[int, tuple[float, float]] = {}
    previous_mouths: dict[int, np.ndarray] = {}
    next_id = 0
    detected_frames = 0
    track_rows: list[dict[str, str]] = []
    for time_s, energy in zip(times, energies):
        capture.set(cv2.CAP_PROP_POS_MSEC, float(time_s) * 1000.0)
        ok, frame = capture.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detect_faces(gray, cascade)
        if faces:
            detected_frames += 1
        current, next_id = assign_tracks(previous_centers, faces, next_id)
        centers = {}
        for track_id, face in current.items():
            x, y, w, h = face
            centers[track_id] = (x + w / 2, y + h / 2)
            mouth = gray[y + int(h * 0.48) : y + int(h * 0.95), x : x + w]
            motion = mouth_motion(previous_mouths.get(track_id), gray, face)
            previous_mouths[track_id] = mouth.copy()
            # Audio is shared by every face; motion differentiates candidate faces.
            score = float(np.clip(0.60 * energy + 0.40 * min(1.0, motion * 8.0), 0.0, 1.0))
            tracks.setdefault(track_id, []).append(score)
            track_rows.append({
                "utterance_id": str(row.get("utterance_id", "")),
                "face_track_id": f"FACE_{track_id:02d}",
                "frame_time_seconds": f"{time_s:.3f}",
                "audio_energy_score": f"{energy:.6f}",
                "mouth_motion_score": f"{motion:.6f}",
                "active_speaker_score": f"{score:.6f}",
            })
        previous_centers = centers
    capture.release()

    best_id, best_score = "", 0.0
    ratios: dict[int, float] = {}
    for track_id, scores in tracks.items():
        values = np.asarray(scores, dtype=np.float32)
        mean_score = float(values.mean()) if values.size else 0.0
        ratio = float(np.mean(values >= args.active_threshold)) if values.size else 0.0
        ratios[track_id] = ratio
        if mean_score > best_score:
            best_id, best_score = track_id, mean_score
    best_ratio = ratios.get(int(best_id), 0.0) if best_id else 0.0
    face_detected = "YES" if detected_frames else "NO"
    active = "YES" if best_id and best_score >= args.score_threshold and best_ratio >= args.frame_ratio_threshold else "NO"
    if not video_path.exists() or not tracks:
        status = "FAILED_NO_FACE_DATA" if video_path.exists() else "FAILED_MISSING_VIDEO"
        active = "UNKNOWN"
    else:
        status = "OK_BASELINE"

    output.update({
        "face_detected": face_detected,
        "face_track_id": f"FACE_{int(best_id):02d}" if best_id else "",
        "active_speaker_detected": active,
        "active_speaker_confidence": f"{best_score:.6f}",
        "active_speaker_frame_ratio": f"{best_ratio:.6f}",
        "speaker_face_match": str(row.get("speaker_face_match", "UNKNOWN") or "UNKNOWN").upper(),
        "speaker_face_match_confidence": str(row.get("speaker_face_match_confidence", "") or ""),
        "target_witness_visible": str(row.get("target_witness_visible", "UNKNOWN") or "UNKNOWN").upper(),
        "target_witness_speaking": str(row.get("target_witness_speaking", "UNKNOWN") or "UNKNOWN").upper(),
        "visual_emotion_eligible": "YES" if active == "YES" and str(row.get("target_witness_visible", "")).upper() == "YES" and str(row.get("speaker_face_match", "")).upper() == "YES" else "NO",
        "asd_model": "audio_energy_plus_mouth_motion_baseline",
        "asd_status": status,
    })
    return output, track_rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-csv", required=True)
    p.add_argument("--output-csv", required=True)
    p.add_argument("--tracks-csv", required=True)
    p.add_argument("--summary-json", required=True)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--max-rows", type=int, default=0)
    p.add_argument("--score-threshold", type=float, default=0.45)
    p.add_argument("--active-threshold", type=float, default=0.45)
    p.add_argument("--frame-ratio-threshold", type=float, default=0.60)
    p.add_argument("--skip-existing", action="store_true")
    args = p.parse_args()
    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if args.max_rows > 0:
        df = df.head(args.max_rows).copy()
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        raise SystemExit(f"Could not load face detector: {cascade_path}")

    output_path, tracks_path, summary_path = map(Path, (args.output_csv, args.tracks_csv, args.summary_json))
    existing = pd.read_csv(output_path, dtype=str).fillna("") if args.skip_existing and output_path.exists() else None
    existing_by_id = existing.set_index("utterance_id").to_dict("index") if existing is not None and "utterance_id" in existing else {}
    rows, track_rows, created, reused, failed = [], [], 0, 0, 0
    for _, row in df.iterrows():
        sample_id = str(row.get("utterance_id", ""))
        if sample_id in existing_by_id:
            rows.append(existing_by_id[sample_id])
            reused += 1
            continue
        try:
            enriched, tracks = process_row(row, cascade, args)
            rows.append(enriched)
            track_rows.extend(tracks)
            created += 1
        except Exception as exc:
            failed += 1
            enriched = row.to_dict()
            enriched.update({"face_detected": "UNKNOWN", "active_speaker_detected": "UNKNOWN", "active_speaker_confidence": "", "active_speaker_frame_ratio": "", "speaker_face_match": "UNKNOWN", "target_witness_visible": "UNKNOWN", "target_witness_speaking": "UNKNOWN", "visual_emotion_eligible": "NO", "asd_model": "audio_energy_plus_mouth_motion_baseline", "asd_status": f"FAILED:{exc}"})
            rows.append(enriched)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tracks_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    pd.DataFrame(track_rows).to_csv(tracks_path, index=False)
    summary = {
        "input_csv": str(args.input_csv),
        "output_csv": str(output_path),
        "tracks_csv": str(tracks_path),
        "rows_processed": len(rows),
        "rows_created": created,
        "rows_reused": reused,
        "rows_failed": failed,
        "asd_model": "audio_energy_plus_mouth_motion_baseline",
        "score_threshold": args.score_threshold,
        "active_frame_ratio_threshold": args.frame_ratio_threshold,
        "visual_emotion_gate": "active_speaker_detected=YES AND target_witness_visible=YES AND speaker_face_match=YES",
        "notes": [
            "This baseline is an ASD screening signal, not a validated TalkNet/AVA model.",
            "Pyannote identifies the audio speaker; this stage estimates which detected face is synchronized with speech.",
            "Speaker-face identity remains UNKNOWN until manually mapped or independently verified.",
            "Face visibility or ViT embeddings alone do not prove that the visible person is speaking.",
            "Thresholds are starting points and require validation against manually reviewed clips.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
