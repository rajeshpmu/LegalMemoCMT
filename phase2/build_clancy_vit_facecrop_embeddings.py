from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Inference uses PyTorch/Hugging Face only. Avoid an unnecessary TensorFlow
# import in transformers on macOS.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

import cv2
import numpy as np
import pandas as pd
import torch

try:
    from transformers import AutoImageProcessor, AutoModel
except Exception as exc:  # pragma: no cover
    raise ImportError("transformers is required for ViT embedding extraction") from exc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_meld_vit_facecrop_manifest import crop_face_frame, get_face_cascade  # noqa: E402
from src.data.preprocessing import PreprocessConfig, sample_video_frames  # noqa: E402


def extract_embeddings(video_path: Path, cfg: PreprocessConfig, processor, model, device, batch_size: int) -> np.ndarray:
    frames = sample_video_frames(str(video_path), cfg)
    if frames.size == 0:
        return np.zeros((cfg.num_frames, int(model.config.hidden_size)), dtype=np.float32)

    cascade = get_face_cascade()
    face_frames = [crop_face_frame(frame, cfg, cascade) for frame in frames]
    face_frames = np.clip(np.asarray(face_frames) * 255.0, 0, 255).astype(np.uint8)
    chunks: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(face_frames), batch_size):
            batch = face_frames[start : start + batch_size]
            inputs = processor(images=list(batch), return_tensors="pt")
            inputs = {key: value.to(device) for key, value in inputs.items()}
            outputs = model(**inputs)
            chunks.append(outputs.last_hidden_state[:, 0, :].detach().cpu().numpy().astype(np.float32))
    return np.concatenate(chunks, axis=0).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Clancy face-cropped ViT embeddings and link them in a manifest")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--vit-model", default="google/vit-base-patch16-224-in21k")
    parser.add_argument("--frame-size", type=int, default=224)
    parser.add_argument("--num-frames", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-rows", type=int, default=0, help="0 means all rows")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output_csv)
    output_root = Path(args.output_root)
    summary_path = Path(args.summary_json)
    frame_cfg = PreprocessConfig(frame_size=args.frame_size, num_frames=args.num_frames)
    df = pd.read_csv(input_path)
    if "video_path" not in df.columns:
        raise ValueError("Input manifest must contain video_path")
    if args.max_rows > 0:
        df = df.head(args.max_rows).copy()

    device = torch.device(args.device)
    processor = AutoImageProcessor.from_pretrained(args.vit_model)
    model = AutoModel.from_pretrained(args.vit_model).to(device)
    hidden_size = int(model.config.hidden_size)
    cascade = cv2.data.haarcascades
    if not cascade:
        raise RuntimeError("OpenCV Haar cascade path is unavailable")

    created = reused = failed = 0
    issues: list[dict[str, str]] = []
    feature_paths: list[str] = []
    statuses: list[str] = []
    for index, row in df.iterrows():
        video_path = Path(str(row.get("video_path", "")).strip())
        youtube_id = str(row.get("youtube_id", "unknown_source")).strip() or "unknown_source"
        sample_id = str(row.get("utterance_id") or row.get("turn_id") or f"row_{index}").strip()
        feature_path = output_root / youtube_id / f"{sample_id}.npy"
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not video_path.exists():
                raise FileNotFoundError(video_path)
            reuse = False
            if args.skip_existing and feature_path.exists():
                existing = np.load(feature_path, allow_pickle=False, mmap_mode="r")
                reuse = existing.ndim == 2 and existing.shape[1] == hidden_size and np.isfinite(existing).all()
            if reuse:
                reused += 1
                status = "reused"
            else:
                embeddings = extract_embeddings(video_path, frame_cfg, processor, model, device, args.batch_size)
                if embeddings.ndim != 2 or embeddings.shape[1] != hidden_size:
                    raise ValueError(f"Unexpected embedding shape {embeddings.shape}; expected (*, {hidden_size})")
                if not np.isfinite(embeddings).all():
                    raise ValueError("Embedding contains non-finite values")
                np.save(feature_path, embeddings)
                created += 1
                status = "created"
            feature_paths.append(str(feature_path.resolve()))
            statuses.append(status)
        except Exception as exc:
            failed += 1
            feature_paths.append("")
            statuses.append("failed")
            issues.append({"sample_id": sample_id, "video_path": str(video_path), "error": str(exc)})

    df["raw_video_path"] = df["video_path"]
    df["video_features_path"] = feature_paths
    df["video_features_status"] = statuses
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "output_root": str(output_root),
        "rows_selected": len(df),
        "embeddings_created": created,
        "embeddings_reused": reused,
        "failed_rows": failed,
        "vit_model": args.vit_model,
        "embedding_shape": [args.num_frames, hidden_size],
        "embedding_dtype": "float32",
        "face_crop_method": "Haar largest-face crop with padded bounding box; center-crop fallback",
        "device": str(device),
        "issues": issues,
        "notes": [
            "raw_video_path preserves the original MP4 provenance.",
            "video_features_path is the path consumed by the Phase 1 video loader.",
            "This stage does not alter audio or text paths and does not create new clips.",
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
