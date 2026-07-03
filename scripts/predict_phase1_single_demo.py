#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import collate_samples, load_manifest
from src.models import LegalMemoCMTPhase1, ModelConfig
from src.train.train import apply_modality_mask, build_dataset, parse_encoder_mode, parse_fusion_mode, parse_modalities, parse_pooling


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
    parser = argparse.ArgumentParser(description="Run single-example Phase 1 inference for a MELD demo video.")
    parser.add_argument("--manifest", required=True, help="Manifest CSV that contains the sample.")
    parser.add_argument("--checkpoint", required=True, help="Trained model checkpoint.")
    parser.add_argument("--sample-id", required=True, help="MELD sample_id to run, e.g. test_dia0_utt0.")
    parser.add_argument("--device", default="cpu", help="cpu, cuda, mps, or auto")
    parser.add_argument("--modalities", default="text,audio,video", help="Comma-separated modalities to keep.")
    parser.add_argument("--fusion-pooling", default="", help="Override pooling if needed.")
    parser.add_argument("--fusion-mode", default="", help="Override fusion mode if needed.")
    parser.add_argument("--encoder-mode", default="", help="Override encoder mode if needed.")
    parser.add_argument("--output-json", default="", help="Optional output JSON path.")
    parser.add_argument("--top-k", type=int, default=3, help="How many top classes to print.")
    args = parser.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    loaded_cfg = checkpoint.get("model_cfg", {})
    if args.fusion_pooling.strip():
        loaded_cfg["fusion_pooling"] = parse_pooling(args.fusion_pooling)
    else:
        loaded_cfg["fusion_pooling"] = parse_pooling(str(loaded_cfg.get("fusion_pooling", "mean")))
    if args.fusion_mode.strip():
        loaded_cfg["fusion_mode"] = parse_fusion_mode(args.fusion_mode)
    else:
        loaded_cfg["fusion_mode"] = parse_fusion_mode(str(loaded_cfg.get("fusion_mode", "legacy")))
    if args.encoder_mode.strip():
        loaded_cfg["encoder_mode"] = parse_encoder_mode(args.encoder_mode)
    else:
        loaded_cfg["encoder_mode"] = parse_encoder_mode(str(loaded_cfg.get("encoder_mode", "legacy")))
    model_cfg = ModelConfig(**loaded_cfg)

    samples = load_manifest(args.manifest)
    chosen = [s for s in samples if s.sample_id == args.sample_id]
    if not chosen:
        raise ValueError(f"Sample id '{args.sample_id}' was not found in {args.manifest}")

    modalities = parse_modalities(args.modalities)
    model_cfg.use_video = "video" in modalities
    dataset = build_dataset(chosen, model_cfg, modalities)
    batch = collate_samples([dataset[0]])

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"))
    else:
        device = torch.device(args.device)

    model = LegalMemoCMTPhase1(model_cfg).to(device)
    missing, unexpected = model.load_state_dict(checkpoint["model_state"], strict=False)
    if missing:
        print(f"Missing keys during load: {sorted(missing)}")
    if unexpected:
        print(f"Unexpected keys during load: {sorted(unexpected)}")
    model.eval()

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
    outputs = apply_modality_mask(batch_tensors, modalities, model.config.encoder_mode)
    if parse_encoder_mode(model.config.encoder_mode) in {"pretrained", "paper"}:
        text_input_ids, text_attention_mask, audio_waveform, audio_attention_mask, video_features, video_mask = outputs
        logits = model(
            text_input_ids=text_input_ids,
            text_attention_mask=text_attention_mask,
            audio_waveform=audio_waveform,
            audio_attention_mask=audio_attention_mask,
            video_features=video_features,
            video_mask=video_mask,
        )
    else:
        text_tokens, audio_features, audio_mask, video_features, video_mask = outputs
        logits = model(
            text_tokens=text_tokens,
            audio_features=audio_features,
            audio_mask=audio_mask,
            video_features=video_features,
            video_mask=video_mask,
        )

    probs = torch.softmax(logits, dim=-1).squeeze(0)
    topk = torch.topk(probs, k=min(args.top_k, probs.numel()))
    pred = int(torch.argmax(probs).item())
    actual = int(batch["label"][0])

    print("Single-video Phase 1 demo")
    print(f"sample_id: {batch['sample_id'][0]}")
    print(f"split: {batch['split'][0]}")
    print(f"ground_truth_label: {actual} ({label_name(actual)})")
    print(f"predicted_label: {pred} ({label_name(pred)})")
    print(f"correct: {pred == actual}")
    print(f"transcript: {batch.get('transcript', [''])[0] if isinstance(batch.get('transcript'), list) else ''}")
    print("top_k:")
    for idx, score in zip(topk.indices.tolist(), topk.values.tolist()):
        print(f"  - {idx} ({label_name(idx)}): {score:.4f}")
    print("paths:")
    if "video_path" in batch:
        print(f"  video_path: {batch['video_path'][0]}")
    if "audio_path" in batch:
        print(f"  audio_path: {batch['audio_path'][0]}")
    if "text_path" in batch:
        print(f"  text_path: {batch['text_path'][0]}")

    result = {
        "sample_id": batch["sample_id"][0],
        "split": batch["split"][0],
        "ground_truth_label": actual,
        "ground_truth_name": label_name(actual),
        "predicted_label": pred,
        "predicted_name": label_name(pred),
        "correct": pred == actual,
        "top_k": [
            {"label": int(idx), "name": label_name(int(idx)), "probability": float(score)}
            for idx, score in zip(topk.indices.tolist(), topk.values.tolist())
        ],
        "video_path": batch.get("video_path", [""])[0] if "video_path" in batch else "",
        "audio_path": batch.get("audio_path", [""])[0] if "audio_path" in batch else "",
    }

    if args.output_json.strip():
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote result JSON to {out}")


if __name__ == "__main__":
    main()
