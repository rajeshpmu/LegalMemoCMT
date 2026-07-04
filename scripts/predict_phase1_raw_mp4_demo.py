#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import ManifestDataset, MultimodalSample, collate_samples, load_manifest
from src.models import LegalMemoCMTPhase1, ModelConfig
from src.train.train import apply_modality_mask, parse_encoder_mode, parse_fusion_mode, parse_modalities, parse_pooling

from scripts.build_meld_vit_facecue_manifest import extract_vit_face_embeddings
from scripts.build_meld_vit_facecrop_manifest import extract_vit_facecrop_embeddings
from src.data.preprocessing import PreprocessConfig, load_audio_waveform, normalize_text

try:
    from transformers import AutoImageProcessor, AutoModel, AutoTokenizer
except Exception:  # pragma: no cover
    AutoImageProcessor = None  # type: ignore[assignment]
    AutoModel = None  # type: ignore[assignment]
    AutoTokenizer = None  # type: ignore[assignment]


MELD_LABELS = {
    0: "neutral",
    1: "joy",
    2: "surprise",
    3: "sadness",
    4: "anger",
    5: "fear",
    6: "disgust",
}


def label_name(label: int) -> str:
    return MELD_LABELS.get(int(label), str(label))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a raw-mp4-to-prediction Phase 1 demo.")
    parser.add_argument("--manifest", required=True, help="Manifest CSV used to recover transcript/audio/label metadata.")
    parser.add_argument("--checkpoint", required=True, help="Trained Phase 1 checkpoint.")
    parser.add_argument("--sample-id", required=True, help="Sample id to read from the manifest.")
    parser.add_argument("--video-path", required=True, help="Raw .mp4 path to process directly.")
    parser.add_argument("--vision-mode", default="facecrop", choices=["facecrop", "fullframe"], help="How to preprocess frames before ViT.")
    parser.add_argument("--device", default="cpu", help="cpu, cuda, mps, or auto")
    parser.add_argument("--modalities", default="text,audio,video", help="Comma-separated modalities to use.")
    parser.add_argument("--fusion-pooling", default="", help="Override pooling if needed.")
    parser.add_argument("--fusion-mode", default="", help="Override fusion mode if needed.")
    parser.add_argument("--encoder-mode", default="", help="Override encoder mode if needed.")
    parser.add_argument("--cache-dir", default="results/phase1_review_demo/raw_mp4_cache", help="Where to cache extracted .npy features.")
    parser.add_argument("--output-json", default="", help="Optional JSON output path.")
    parser.add_argument("--top-k", type=int, default=3, help="How many top classes to print.")
    parser.add_argument("--vit-batch-size", type=int, default=8, help="Frame batch size for ViT extraction.")
    args = parser.parse_args()

    if AutoImageProcessor is None or AutoModel is None:
        raise ImportError("transformers is required for the raw mp4 demo")

    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    loaded_cfg = checkpoint.get("model_cfg", {})
    loaded_cfg["fusion_pooling"] = parse_pooling(args.fusion_pooling or loaded_cfg.get("fusion_pooling", "mean"))
    loaded_cfg["fusion_mode"] = parse_fusion_mode(args.fusion_mode or loaded_cfg.get("fusion_mode", "legacy"))
    loaded_cfg["encoder_mode"] = parse_encoder_mode(args.encoder_mode or loaded_cfg.get("encoder_mode", "legacy"))
    model_cfg = ModelConfig(**loaded_cfg)

    samples = load_manifest(args.manifest)
    matches = [s for s in samples if s.sample_id == args.sample_id]
    if not matches:
        raise ValueError(f"Sample id '{args.sample_id}' was not found in {args.manifest}")
    row = matches[0]

    modalities = parse_modalities(args.modalities)
    model_cfg.use_video = "video" in modalities

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"))
    else:
        device = torch.device(args.device)

    preprocess_cfg = PreprocessConfig(
        frame_size=224,
        num_frames=model_cfg.max_video_len,
        sample_rate=16000,
        max_audio_seconds=10.0,
    )

    image_processor = AutoImageProcessor.from_pretrained("google/vit-base-patch16-224-in21k")
    vit_model = AutoModel.from_pretrained("google/vit-base-patch16-224-in21k").to(device)
    tokenizer = None
    if model_cfg.encoder_mode in {"pretrained", "paper"}:
        if AutoTokenizer is None:
            raise ImportError("transformers tokenizer support is required for pretrained encoder mode")
        tokenizer = AutoTokenizer.from_pretrained(model_cfg.text_model_name, use_fast=False)

    if args.vision_mode == "facecrop":
        video_features = extract_vit_facecrop_embeddings(
            args.video_path,
            preprocess_cfg,
            image_processor,
            vit_model,
            device,
            batch_size=args.vit_batch_size,
        )
    else:
        video_features = extract_vit_face_embeddings(
            args.video_path,
            preprocess_cfg,
            image_processor,
            vit_model,
            device,
            batch_size=args.vit_batch_size,
        )

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_feature_path = cache_dir / f"{args.sample_id}_{args.vision_mode}.npy"
    np.save(cached_feature_path, video_features)

    sample = MultimodalSample(
        sample_id=row.sample_id,
        split=row.split,
        label=row.label,
        video_path=str(cached_feature_path),
        audio_path=args.video_path,
        transcript=normalize_text(row.transcript),
        video_features=video_features,
    )

    dataset_obj = ManifestDataset(
        [sample],
        tokenizer=tokenizer,
        encoder_mode=model_cfg.encoder_mode,
        # Keep the freshly extracted ViT embeddings instead of falling back to
        # an empty placeholder tensor. The demo already materializes the
        # correct .npy cache above.
        load_video=True,
        preprocess_cfg=preprocess_cfg,
    )
    batch = collate_samples([dataset_obj[0]])
    batch_tensors = {
        "text_tokens": torch.as_tensor(batch["text_tokens"], device=device) if "text_tokens" in batch else None,
        "text_input_ids": torch.as_tensor(batch["text_input_ids"], device=device) if "text_input_ids" in batch else None,
        "text_attention_mask": torch.as_tensor(batch["text_attention_mask"], device=device) if "text_attention_mask" in batch else None,
        "audio_features": torch.as_tensor(batch["audio_features"], device=device) if "audio_features" in batch else None,
        "audio_waveform": torch.as_tensor(batch["audio_waveform"], device=device) if "audio_waveform" in batch else None,
        "audio_mask": torch.as_tensor(batch["audio_mask"], device=device) if "audio_mask" in batch else None,
        "audio_attention_mask": torch.as_tensor(batch["audio_attention_mask"], device=device) if "audio_attention_mask" in batch else None,
        "video_features": torch.as_tensor(batch["video_features"], device=device),
        "video_mask": torch.as_tensor(batch["video_mask"], device=device),
    }

    model = LegalMemoCMTPhase1(model_cfg).to(device)
    missing, unexpected = model.load_state_dict(checkpoint["model_state"], strict=False)
    if missing:
        print(f"Missing keys during load: {sorted(missing)}")
    if unexpected:
        print(f"Unexpected keys during load: {sorted(unexpected)}")
    model.eval()

    outputs = apply_modality_mask(batch_tensors, modalities, model.config.encoder_mode)
    if parse_encoder_mode(model.config.encoder_mode) in {"pretrained", "paper"}:
        text_input_ids, text_attention_mask, audio_waveform, audio_attention_mask, video_features_t, video_mask = outputs
        logits = model(
            text_input_ids=text_input_ids,
            text_attention_mask=text_attention_mask,
            audio_waveform=audio_waveform,
            audio_attention_mask=audio_attention_mask,
            video_features=video_features_t,
            video_mask=video_mask,
        )
    else:
        text_tokens, audio_features, audio_mask, video_features_t, video_mask = outputs
        logits = model(
            text_tokens=text_tokens,
            audio_features=audio_features,
            audio_mask=audio_mask,
            video_features=video_features_t,
            video_mask=video_mask,
        )

    probs = torch.softmax(logits, dim=-1).squeeze(0)
    topk = torch.topk(probs, k=min(args.top_k, probs.numel()))
    pred = int(torch.argmax(probs).item())
    confidence = float(probs[pred].item())
    actual = int(row.label)

    print("Raw-mp4 Phase 1 demo")
    print(f"sample_id: {row.sample_id}")
    print(f"split: {row.split}")
    print(f"video_path: {args.video_path}")
    print(f"cached_video_features: {cached_feature_path}")
    print(f"ground_truth_label: {actual} ({label_name(actual)})")
    print(f"predicted_label: {pred} ({label_name(pred)})")
    print(f"confidence: {confidence:.4f}")
    print(f"correct: {pred == actual}")
    print("top_k:")
    for idx, score in zip(topk.indices.tolist(), topk.values.tolist()):
        print(f"  - {idx} ({label_name(idx)}): {score:.4f}")

    result = {
        "sample_id": row.sample_id,
        "split": row.split,
        "video_path": args.video_path,
        "cached_video_features": str(cached_feature_path),
        "ground_truth_label": actual,
        "ground_truth_name": label_name(actual),
        "predicted_label": pred,
        "predicted_name": label_name(pred),
        "confidence": confidence,
        "correct": pred == actual,
        "top_k": [
            {"label": int(idx), "name": label_name(int(idx)), "probability": float(score)}
            for idx, score in zip(topk.indices.tolist(), topk.values.tolist())
        ],
    }

    if args.output_json.strip():
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote result JSON to {out}")


if __name__ == "__main__":
    main()
