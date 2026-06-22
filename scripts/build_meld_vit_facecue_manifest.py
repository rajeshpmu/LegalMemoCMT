from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def extract_vit_face_embeddings(
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

    frames = np.clip(frames * 255.0, 0, 255).astype(np.uint8)
    embeddings: list[np.ndarray] = []

    vit_model.eval()
    with torch.no_grad():
        for start in range(0, len(frames), batch_size):
            batch = frames[start : start + batch_size]
            inputs = image_processor(images=list(batch), return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            outputs = vit_model(**inputs)
            hidden = outputs.last_hidden_state[:, 0, :].detach().cpu().numpy().astype(np.float32)
            embeddings.append(hidden)

    if embeddings:
        return np.concatenate(embeddings, axis=0).astype(np.float32)
    return np.zeros((cfg.num_frames, vit_model.config.hidden_size), dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a MELD manifest with ViT facial-cue embeddings")
    parser.add_argument("--meld-root", type=str, default="data/MELD", help="Path to MELD dataset root")
    parser.add_argument(
        "--output-root",
        type=str,
        default="data/processed/MELD_VIT_FACECUE",
        help="Directory for extracted ViT facial-cue features",
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
        raise ImportError("transformers is required to build the ViT facial-cue manifest")

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
                    vit_embeddings = extract_vit_face_embeddings(
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

    out_csv = manifest_dir / "meld_vit_facecue.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Wrote {len(rows)} rows to {out_csv}")
    if skipped:
        print(f"Skipped {skipped} unreadable samples")


if __name__ == "__main__":
    main()
