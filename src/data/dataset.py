from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    pd = None  # type: ignore[assignment]

from .preprocessing import PreprocessConfig, extract_video_features, load_audio_features, load_audio_waveform, normalize_text


PHASE2_EMOTION_LABEL_MAP = {
    "neutral": 0,
    "fear": 1,
    "anger": 2,
    "sadness": 3,
    "stress": 4,
    "confidence": 5,
}


def _clean_text(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    if text.lower().startswith("<!doctype html>") or text.lower().startswith("<html") or text.lower().startswith("<head") or text.lower().startswith("<body"):
        return ""
    return text


@dataclass
class MultimodalSample:
    sample_id: str
    split: str
    label: int
    video_path: str = ""
    audio_path: str = ""
    transcript: str = ""
    text_tokens: Optional[np.ndarray] = None
    audio_features: Optional[np.ndarray] = None
    video_features: Optional[np.ndarray] = None


def load_manifest(path: str | Path) -> list[MultimodalSample]:
    if pd is None:
        raise ImportError("pandas is required to load a CSV manifest")
    df = pd.read_csv(path)
    required = {"split", "video_path", "audio_path"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Manifest is missing required columns: {sorted(missing)}")

    samples: list[MultimodalSample] = []
    for _, row in df.iterrows():
        sample_id = str(row.get("sample_id") or row.get("utterance_id") or row.get("manifest_id") or "").strip()
        if not sample_id:
            raise ValueError("Manifest row is missing a sample_id/utterance_id/manifest_id value")

        label_value = row.get("label", None)
        if label_value is None or (isinstance(label_value, float) and pd.isna(label_value)):
            label_value = row.get("emotion_label", None)
        if label_value is None or (isinstance(label_value, str) and not label_value.strip()):
            raise ValueError(f"Manifest row for {sample_id} is missing a label or emotion_label value")
        label_text = str(label_value).strip()
        if label_text.isdigit():
            label = int(label_text)
        else:
            try:
                label = int(float(label_text))
            except Exception:
                mapped = PHASE2_EMOTION_LABEL_MAP.get(label_text.lower())
                if mapped is None:
                    raise ValueError(f"Unsupported label value for {sample_id}: {label_text}")
                label = mapped

        transcript = _clean_text(row.get("transcript") or row.get("utterance_text") or row.get("text") or "")
        samples.append(
            MultimodalSample(
                sample_id=sample_id,
                split=str(row["split"]),
                label=label,
                video_path=_clean_text(row.get("video_path", "")),
                audio_path=_clean_text(row.get("audio_path", "")),
                transcript=transcript,
            )
        )
    return samples


class ManifestDataset:
    """Lightweight dataset wrapper for Phase 1."""

    def __init__(
        self,
        samples: Iterable[MultimodalSample],
        tokenizer=None,
        max_text_len: int = 128,
        max_audio_len: int = 256,
        max_video_len: int = 32,
        preprocess_cfg: PreprocessConfig | None = None,
        encoder_mode: str = "legacy",
        load_video: bool = True,
    ) -> None:
        self.samples = list(samples)
        self.tokenizer = tokenizer
        self.max_text_len = max_text_len
        self.max_audio_len = max_audio_len
        self.max_video_len = max_video_len
        self.preprocess_cfg = preprocess_cfg or PreprocessConfig(num_frames=max_video_len)
        self.encoder_mode = encoder_mode.lower().strip()
        self.load_video = load_video

    def __len__(self) -> int:
        return len(self.samples)

    def _encode_text_legacy(self, transcript: str) -> np.ndarray:
        if self.tokenizer is None:
            tokens = [min(len(tok), 255) for tok in transcript.split()]
        else:
            tokens = self.tokenizer(transcript)
        tokens = tokens[: self.max_text_len]
        if len(tokens) < self.max_text_len:
            tokens = tokens + [0] * (self.max_text_len - len(tokens))
        return np.asarray(tokens, dtype=np.int64)

    def _encode_text_pretrained(self, transcript: str) -> tuple[np.ndarray, np.ndarray]:
        if self.tokenizer is None:
            raise ValueError("A HuggingFace tokenizer is required in pretrained encoder mode")
        encoded = self.tokenizer(
            normalize_text(transcript),
            truncation=True,
            padding="max_length",
            max_length=self.max_text_len,
            return_attention_mask=True,
        )
        input_ids = np.asarray(encoded["input_ids"], dtype=np.int64)
        attention_mask = np.asarray(encoded["attention_mask"], dtype=np.int64)
        return input_ids, attention_mask

    def _load_array(self, path: str, default_shape: tuple[int, int]) -> np.ndarray:
        if path and Path(path).exists():
            try:
                p = Path(path)
                if p.suffix.lower() == ".npy":
                    arr = np.load(p, allow_pickle=False)
                    arr = np.asarray(arr, dtype=np.float32)
                elif p.suffix.lower() in {".wav", ".mp3", ".flv", ".mp4", ".m4a", ".avi"}:
                    # Treat non-NPY inputs as raw media and derive features on demand.
                    if default_shape[0] == self.max_audio_len:
                        arr = load_audio_features(str(p), self.preprocess_cfg)
                    else:
                        arr = extract_video_features(str(p), self.preprocess_cfg)
                else:
                    arr = np.zeros(default_shape, dtype=np.float32)
                arr = np.nan_to_num(np.asarray(arr, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
                if arr.ndim == 0 or arr.size == 0:
                    return np.zeros(default_shape, dtype=np.float32)
                if not np.isfinite(arr).all():
                    return np.zeros(default_shape, dtype=np.float32)
                return arr
            except Exception:
                return np.zeros(default_shape, dtype=np.float32)
        return np.zeros(default_shape, dtype=np.float32)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        sample = self.samples[idx]
        use_pretrained = self.encoder_mode in {"pretrained", "paper"}
        if use_pretrained:
            text_input_ids, text_attention_mask = self._encode_text_pretrained(sample.transcript)
            waveform_len = int(self.preprocess_cfg.max_audio_seconds * self.preprocess_cfg.sample_rate)
            audio_waveform = load_audio_waveform(sample.audio_path, self.preprocess_cfg) if sample.audio_path else np.zeros(waveform_len, dtype=np.float32)
            if self.load_video:
                video_features = sample.video_features if sample.video_features is not None else self._load_array(sample.video_path, (self.max_video_len, 128))
            else:
                video_features = np.zeros((self.max_video_len, 128), dtype=np.float32)
        else:
            text_tokens = sample.text_tokens if sample.text_tokens is not None else self._encode_text_legacy(sample.transcript)
            audio_features = sample.audio_features if sample.audio_features is not None else self._load_array(sample.audio_path, (self.max_audio_len, 128))
            if self.load_video:
                video_features = sample.video_features if sample.video_features is not None else self._load_array(sample.video_path, (self.max_video_len, 128))
            else:
                video_features = np.zeros((self.max_video_len, 128), dtype=np.float32)

        video_features = np.nan_to_num(np.asarray(video_features, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        if use_pretrained:
            audio_waveform = np.nan_to_num(np.asarray(audio_waveform, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
            return {
                "sample_id": sample.sample_id,
                "split": sample.split,
                "label": np.int64(sample.label),
                "text_input_ids": text_input_ids,
                "text_attention_mask": text_attention_mask,
                "audio_waveform": audio_waveform,
                "video_features": video_features,
            }

        audio_features = np.nan_to_num(np.asarray(audio_features, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        if audio_features.ndim == 1:
            audio_features = audio_features.reshape(-1, 1)
        if video_features.ndim == 1:
            video_features = video_features.reshape(-1, 1)
        return {
            "sample_id": sample.sample_id,
            "split": sample.split,
            "label": np.int64(sample.label),
            "text_tokens": text_tokens,
            "audio_features": audio_features,
            "video_features": video_features,
        }


def collate_samples(batch: list[dict[str, Any]]) -> dict[str, Any]:
    labels = np.asarray([b["label"] for b in batch], dtype=np.int64)
    sample_ids = [b["sample_id"] for b in batch]
    split = [b["split"] for b in batch]

    use_pretrained = "text_input_ids" in batch[0]

    def pad_1d(arrays: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        max_len = max(a.shape[0] for a in arrays)
        out = np.zeros((len(arrays), max_len), dtype=np.float32)
        mask = np.zeros((len(arrays), max_len), dtype=np.bool_)
        for i, arr in enumerate(arrays):
            length = arr.shape[0]
            out[i, :length] = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
            mask[i, :length] = True
        return out, mask

    def pad_2d(arrays: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        max_len = max(a.shape[0] for a in arrays)
        feat_dim = arrays[0].shape[1]
        out = np.zeros((len(arrays), max_len, feat_dim), dtype=np.float32)
        mask = np.zeros((len(arrays), max_len), dtype=np.bool_)
        for i, arr in enumerate(arrays):
            length = arr.shape[0]
            out[i, :length] = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
            mask[i, :length] = True
        return out, mask

    if use_pretrained:
        text_input_ids = np.stack([b["text_input_ids"] for b in batch], axis=0)
        text_attention_mask = np.stack([b["text_attention_mask"] for b in batch], axis=0)
        audio_waveform, audio_mask = pad_1d([b["audio_waveform"] for b in batch])
        video_features, video_mask = pad_2d([b["video_features"] for b in batch])
        return {
            "sample_id": sample_ids,
            "split": split,
            "label": labels,
            "text_input_ids": text_input_ids,
            "text_attention_mask": text_attention_mask,
            "audio_waveform": audio_waveform,
            "audio_attention_mask": audio_mask,
            "video_features": video_features,
            "video_mask": video_mask,
        }

    text_tokens = np.stack([b["text_tokens"] for b in batch], axis=0)
    audio_features, audio_mask = pad_2d([b["audio_features"] for b in batch])
    video_features, video_mask = pad_2d([b["video_features"] for b in batch])

    return {
        "sample_id": sample_ids,
        "split": split,
        "label": labels,
        "text_tokens": text_tokens,
        "audio_features": audio_features,
        "audio_mask": audio_mask,
        "video_features": video_features,
        "video_mask": video_mask,
    }
