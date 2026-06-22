from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch

try:
    from transformers import AutoImageProcessor, AutoModel
except Exception:  # pragma: no cover
    AutoImageProcessor = None  # type: ignore[assignment]
    AutoModel = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_meld_manifest import EMOTION_MAP, find_meld_clip
from src.data.preprocessing import PreprocessConfig, normalize_text, sample_video_frames


def get_face_cascade() -> cv2.CascadeClassifier:
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        raise RuntimeError(f"Could not load Haar face cascade from {cascade_path}")
    return cascade


def center_crop_square(frame_rgb: np.ndarray) -> np.ndarray:
    h, w = frame_rgb.shape[:2]
    side = min(h, w)
    top = max((h - side) // 2, 0)
    left = max((w - side) // 2, 0)
    crop = frame_rgb[top : top + side, left : left + side]
    if crop.size == 0:
        return frame_rgb
    return crop


def crop_face_frame(frame_rgb: np.ndarray, cfg: PreprocessConfig, cascade: cv2.CascadeClassifier) -> np.ndarray:
    frame_uint8 = np.clip(frame_rgb * 255.0, 0, 255).astype(np.uint8)
    gray = cv2.cvtColor(frame_uint8, cv2.COLOR_RGB2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))

    if len(faces) == 0:
        crop = center_crop_square(frame_uint8)
    else:
        x, y, w, h = max(faces, key=lambda box: int(box[2]) * int(box[3]))
        pad_x = max(int(0.15 * w), 4)
        pad_y = max(int(0.15 * h), 4)
        x1 = max(x - pad_x, 0)
        y1 = max(y - pad_y, 0)
        x2 = min(x + w + pad_x, frame_uint8.shape[1])
        y2 = min(y + h + pad_y, frame_uint8.shape[0])
        crop = frame_uint8[y1:y2, x1:x2]
        if crop.size == 0:
            crop = center_crop_square(frame_uint8)

    resized = cv2.resize(crop, (cfg.frame_size, cfg.frame_size), interpolation=cv2.INTER_AREA)
    return resized.astype(np.float32) / 255.0


def extract_vit_facecrop_embeddings(
    video_path: str,
    cfg: PreprocessConfig,
    image_processor,
    vit_model,
    device: torch.device,
    batch_size: int,
) -> np.ndarray:
    frames = sample_video_frames(video_path, cfg)
    if frames.size == 0:
        return np.zeros((cfg.num_frames, vit_model.config.hidden_size), dtype=np.float32)

    cascade = get_face_cascade()
    face_frames = [crop_face_frame(frame, cfg, cascade) for frame in frames]
    face_frames = np.clip(np.asarray(face_frames) * 255.0, 0, 255).astype(np.uint8)
    embeddings: list[np.ndarray] = []

    vit_model.eval()
    with torch.no_grad():
        for start in range(0, len(face_frames), batch_size):
            batch = face_frames[start : start + batch_size]
            inputs = image_processor(images=list(batch), return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            outputs = vit_model(**inputs)
            hidden = outputs.last_hidden_state[:, 0, :].detach().cpu().numpy().astype(np.float32)
            embeddings.append(hidden)

    if embeddings:
        return np.concatenate(embeddings, axis=0).astype(np.float32)
    return np.zeros((cfg.num_frames, vit_model.config.hidden_size), dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a MELD manifest with face-cropped ViT embeddings")
    parser.add_argument("--meld-root", type=str, default="data/MELD", help="Path to MELD dataset root")
    parser.add_argument(
        "--output-root",
        type=str,
        default="data/processed/MELD_VIT_FACECROP",
        help="Directory for extracted ViT face-crop features",
    )
    parser.add_argument(
        "--manifest-dir",
        type=str,
        default="data/manifests",
        help="Directory for the output manifest CSV",
    )
    parser.add_argument(
        "--vit-model",
        type=str,
        default="google/vit-base-patch16-224-in21k",
        help="Pretrained ViT checkpoint used for facial-cue embeddings",
    )
    parser.add_argument("--frame-size", type=int, default=224)
    parser.add_argument("--num-frames", type=int, default=16)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--max-audio-seconds", type=float, default=10.0)
    parser.add_argument("--batch-size", type=int, default=8, help="Frame batch size for ViT embedding extraction")
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args()

    if AutoImageProcessor is None or AutoModel is None:
        raise ImportError("transformers is required to build the ViT face-crop manifest")

    meld_root = Path(args.meld_root)
    ann_dir = meld_root / "annotations"
    output_root = Path(args.output_root)
    manifest_dir = Path(args.manifest_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    cfg = PreprocessConfig(
        frame_size=args.frame_size,
        num_frames=args.num_frames,
        sample_rate=args.sample_rate,
        max_audio_seconds=args.max_audio_seconds,
    )
    device = torch.device(args.device)
    image_processor = AutoImageProcessor.from_pretrained(args.vit_model)
    vit_model = AutoModel.from_pretrained(args.vit_model).to(device)

    rows = []
    skipped = 0
    for split in ["train", "dev", "test"]:
        csv_path = ann_dir / f"{split}_sent_emo.csv"
        if not csv_path.exists():
            print(f"Skipping {split}: missing {csv_path}")
            continue

        df = pd.read_csv(csv_path)
        feat_dir = output_root / split / "video"
        feat_dir.mkdir(parents=True, exist_ok=True)
        for _, row in df.iterrows():
            emotion = str(row["Emotion"]).strip().lower()
            if emotion not in EMOTION_MAP:
                continue
            dialogue_id = int(row["Dialogue_ID"])
            utterance_id = int(row["Utterance_ID"])
            transcript = normalize_text(str(row["Utterance"]))
            try:
                clip_path = find_meld_clip(meld_root / "raw", split, dialogue_id, utterance_id)
                sample_id = f"{split}_dia{dialogue_id}_utt{utterance_id}"
                video_feat_path = feat_dir / f"{sample_id}.npy"
                if not video_feat_path.exists():
                    vit_embeddings = extract_vit_facecrop_embeddings(
                        str(clip_path),
                        cfg,
                        image_processor,
                        vit_model,
                        device,
                        args.batch_size,
                    )
                    np.save(video_feat_path, vit_embeddings)
                rows.append(
                    {
                        "sample_id": sample_id,
                        "split": split,
                        "label": EMOTION_MAP[emotion],
                        "video_path": str(video_feat_path),
                        "audio_path": str(clip_path),
                        "transcript": transcript,
                    }
                )
            except Exception as exc:
                skipped += 1
                print(f"Skipping {split} dia{dialogue_id}_utt{utterance_id}: {exc}")

    out_csv = manifest_dir / "meld_vit_facecrop.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Wrote {len(rows)} rows to {out_csv}")
    if skipped:
        print(f"Skipped {skipped} unreadable samples")


if __name__ == "__main__":
    main()
