from __future__ import annotations

from dataclasses import dataclass
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

try:
    import librosa
except Exception:  # pragma: no cover
    librosa = None  # type: ignore[assignment]

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None  # type: ignore[assignment]

try:
    import imageio_ffmpeg
except Exception:  # pragma: no cover
    imageio_ffmpeg = None  # type: ignore[assignment]


@dataclass
class PreprocessConfig:
    frame_size: int = 224
    num_frames: int = 32
    video_feature_dim: int = 128
    sample_rate: int = 16000
    max_audio_seconds: float = 10.0


def sample_video_frames(video_path: str, cfg: PreprocessConfig) -> np.ndarray:
    if cv2 is None:
        raise ImportError("opencv-python is required for video preprocessing")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    indices = np.linspace(0, total_frames - 1, cfg.num_frames).astype(int)
    frames = []
    index_set = set(indices.tolist())
    current = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if current in index_set:
            frame = cv2.resize(frame, (cfg.frame_size, cfg.frame_size))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame.astype(np.float32) / 255.0)
        current += 1

    cap.release()

    if not frames:
        return np.zeros((cfg.num_frames, cfg.frame_size, cfg.frame_size, 3), dtype=np.float32)

    if len(frames) < cfg.num_frames:
        pad = [np.zeros_like(frames[0]) for _ in range(cfg.num_frames - len(frames))]
        frames.extend(pad)

    return np.stack(frames[: cfg.num_frames], axis=0)


def extract_video_features(video_path: str, cfg: PreprocessConfig) -> np.ndarray:
    """Convert a video into fixed-size per-frame feature vectors.

    This keeps the Phase 1 scaffold runnable without a pretrained visual
    backbone. The output shape is (num_frames, video_feature_dim), which
    matches the current model input.
    """
    frames = sample_video_frames(video_path, cfg)
    gray = frames.mean(axis=-1)  # (T, H, W)
    h, w = gray.shape[1], gray.shape[2]
    # Downsample each frame to a compact 16x8 representation and flatten to 128 dims.
    target_h, target_w = 16, 8
    if cv2 is None:
        raise ImportError("opencv-python is required for video preprocessing")
    compact = []
    for frame in gray:
        resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
        vec = resized.reshape(-1).astype(np.float32)
        if vec.shape[0] < cfg.video_feature_dim:
            vec = np.pad(vec, (0, cfg.video_feature_dim - vec.shape[0]))
        compact.append(vec[: cfg.video_feature_dim])
    features = np.stack(compact, axis=0).astype(np.float32)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    if features.size:
        mean = features.mean(axis=1, keepdims=True)
        std = features.std(axis=1, keepdims=True)
        features = (features - mean) / np.maximum(std, 1e-6)
    return np.clip(features, -5.0, 5.0).astype(np.float32)


def load_audio_features(audio_path: str, cfg: PreprocessConfig) -> np.ndarray:
    waveform, sr = _load_audio_waveform_any(audio_path, cfg)

    max_len = int(cfg.max_audio_seconds * cfg.sample_rate)
    waveform = waveform[:max_len]
    if len(waveform) < max_len:
        waveform = np.pad(waveform, (0, max_len - len(waveform)))

    mel = librosa.feature.melspectrogram(y=waveform, sr=cfg.sample_rate, n_mels=128)
    log_mel = librosa.power_to_db(mel, ref=np.max)
    features = log_mel.T.astype(np.float32)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    features = np.clip(features, -80.0, 80.0)
    if features.size:
        mean = features.mean(axis=1, keepdims=True)
        std = features.std(axis=1, keepdims=True)
        features = (features - mean) / np.maximum(std, 1e-6)
    return np.clip(features, -5.0, 5.0).astype(np.float32)


def _load_audio_with_ffmpeg(audio_path: str, cfg: PreprocessConfig) -> tuple[np.ndarray, int]:
    if imageio_ffmpeg is None:
        raise ImportError("Either librosa or imageio-ffmpeg is required for audio preprocessing")

    if sf is None:
        raise ImportError("soundfile is required for ffmpeg-based audio preprocessing")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(audio_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(cfg.sample_rate),
            str(tmp_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        waveform, sr = sf.read(tmp_path, dtype="float32", always_2d=False)
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=1)
        return np.asarray(waveform, dtype=np.float32), int(sr)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def load_audio_waveform(audio_path: str, cfg: PreprocessConfig) -> np.ndarray:
    """Load a mono waveform at the configured sample rate.

    This is used by the paper-aligned pretrained speech encoder path.
    """
    waveform, _ = _load_audio_waveform_any(audio_path, cfg)

    waveform = np.asarray(waveform, dtype=np.float32)
    max_len = int(cfg.max_audio_seconds * cfg.sample_rate)
    waveform = waveform[:max_len]
    if len(waveform) < max_len:
        waveform = np.pad(waveform, (0, max_len - len(waveform)))
    waveform = np.nan_to_num(waveform, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(waveform, -1.0, 1.0).astype(np.float32)


def _load_audio_waveform_any(audio_path: str, cfg: PreprocessConfig) -> tuple[np.ndarray, int]:
    if librosa is not None:
        try:
            return librosa.load(audio_path, sr=cfg.sample_rate, mono=True)
        except Exception:
            try:
                return _load_audio_with_ffmpeg(audio_path, cfg)
            except Exception:
                max_len = int(cfg.max_audio_seconds * cfg.sample_rate)
                return np.zeros(max_len, dtype=np.float32), cfg.sample_rate
    try:
        return _load_audio_with_ffmpeg(audio_path, cfg)
    except Exception:
        max_len = int(cfg.max_audio_seconds * cfg.sample_rate)
        return np.zeros(max_len, dtype=np.float32), cfg.sample_rate


def normalize_text(text: str) -> str:
    text = text.replace("\n", " ").replace("\t", " ")
    text = " ".join(text.split())
    return text.strip()


def build_feature_manifest_rows(rows: Iterable[dict], output_root: str | Path) -> list[dict]:
    output_root = Path(output_root)
    manifest_rows: list[dict] = []
    for row in rows:
        manifest_rows.append(
            {
                "sample_id": row["sample_id"],
                "split": row["split"],
                "label": row["label"],
                "video_path": str(output_root / row["video_feature_path"]),
                "audio_path": str(output_root / row["audio_feature_path"]),
                "transcript": normalize_text(row.get("transcript", "")),
            }
        )
    return manifest_rows
