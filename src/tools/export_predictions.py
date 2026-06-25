from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import torch

from ..data import collate_samples, load_manifest
from ..metrics import accuracy_score, macro_f1_score, weighted_f1_score
from ..models import LegalMemoCMTPhase1, ModelConfig
from ..train.train import apply_modality_mask, build_dataset, parse_encoder_mode, parse_fusion_mode, parse_modalities, parse_pooling


def parse_modalities(value: str) -> set[str]:
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    allowed = {"text", "audio", "video"}
    modalities = {p for p in parts if p in allowed}
    if not modalities:
        return {"text", "audio", "video"}
    return modalities


def parse_pooling(value: str) -> str:
    value = value.strip().lower()
    return value if value in {"cls", "mean", "max", "min"} else "mean"


def apply_modality_mask(batch, modalities: set[str]):
    if "text_input_ids" in batch:
        text_input_ids = batch["text_input_ids"]
        text_attention_mask = batch["text_attention_mask"]
        audio_waveform = batch["audio_waveform"]
        audio_attention_mask = batch["audio_attention_mask"]
        video_features = batch["video_features"]
        video_mask = batch["video_mask"]

        if "text" not in modalities:
            text_input_ids = torch.zeros_like(text_input_ids)
            text_attention_mask = torch.zeros_like(text_attention_mask)
        if "audio" not in modalities:
            audio_waveform = torch.zeros_like(audio_waveform)
            audio_attention_mask = torch.zeros_like(audio_attention_mask)
        if "video" not in modalities:
            video_features = torch.zeros_like(video_features)
            video_mask = torch.zeros_like(video_mask)
        return text_input_ids, text_attention_mask, audio_waveform, audio_attention_mask, video_features, video_mask

    text_tokens = batch["text_tokens"]
    audio_features = batch["audio_features"]
    audio_mask = batch["audio_mask"]
    video_features = batch["video_features"]
    video_mask = batch["video_mask"]

    if "text" not in modalities:
        text_tokens = torch.zeros_like(text_tokens)
    if "audio" not in modalities:
        audio_features = torch.zeros_like(audio_features)
        audio_mask = torch.zeros_like(audio_mask)
    if "video" not in modalities:
        video_features = torch.zeros_like(video_features)
        video_mask = torch.zeros_like(video_mask)
    return text_tokens, audio_features, audio_mask, video_features, video_mask


def main() -> None:
    parser = argparse.ArgumentParser(description="Export per-sample predictions for LegalMemoCMT Phase 1")
    parser.add_argument("--manifest", type=str, required=True, help="CSV manifest path")
    parser.add_argument("--checkpoint", type=str, required=True, help="Checkpoint path")
    parser.add_argument("--output-csv", type=str, required=True, help="CSV path for per-sample predictions")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--modalities", type=str, default="text,audio,video", help="Comma-separated subset of text,audio,video")
    parser.add_argument("--fusion-pooling", type=str, default="", help="Optional override: cls, mean, max, min")
    parser.add_argument("--fusion-mode", type=str, default="", help="Optional override: legacy, gated")
    parser.add_argument("--encoder-mode", type=str, default="", help="Optional override: legacy, pretrained, paper")
    parser.add_argument("--device", type=str, default="cpu", help="Evaluation device: cpu, cuda, mps, or auto")
    parser.add_argument("--split", type=str, default="", help="Optional manifest split filter (e.g. train, dev, test)")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap on exported rows; 0 exports all rows")
    args = parser.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    loaded_cfg = checkpoint.get("model_cfg", {})
    fusion_pooling = args.fusion_pooling.strip().lower() if args.fusion_pooling.strip() else str(loaded_cfg.get("fusion_pooling", "mean"))
    fusion_mode = args.fusion_mode.strip().lower() if args.fusion_mode.strip() else str(loaded_cfg.get("fusion_mode", "legacy"))
    encoder_mode = args.encoder_mode.strip().lower() if args.encoder_mode.strip() else str(loaded_cfg.get("encoder_mode", "legacy"))
    loaded_cfg["fusion_pooling"] = parse_pooling(fusion_pooling)
    loaded_cfg["fusion_mode"] = parse_fusion_mode(fusion_mode)
    loaded_cfg["encoder_mode"] = parse_encoder_mode(encoder_mode)
    model_cfg = ModelConfig(**loaded_cfg)

    samples = load_manifest(args.manifest)
    if args.split.strip():
        wanted_split = args.split.strip().lower()
        samples = [sample for sample in samples if sample.split.lower() == wanted_split]
        if not samples:
            raise ValueError(f"No samples found for split '{wanted_split}' in {args.manifest}")

    modalities = parse_modalities(args.modalities)
    model_cfg.use_video = "video" in modalities
    dataset = build_dataset(samples, model_cfg, modalities)

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"))
    else:
        device = torch.device(args.device)
    model = LegalMemoCMTPhase1(model_cfg).to(device)
    missing, unexpected = model.load_state_dict(checkpoint["model_state"], strict=False)
    if missing:
        print(f"Missing keys during export load: {sorted(missing)}")
    if unexpected:
        print(f"Unexpected keys during export load: {sorted(unexpected)}")
    model.eval()

    rows: list[dict[str, object]] = []
    y_true: list[np.ndarray] = []
    y_pred: list[np.ndarray] = []

    with torch.no_grad():
        for start in range(0, len(dataset), args.batch_size):
            batch_items = [dataset[i] for i in range(start, min(start + args.batch_size, len(dataset)))]
            batch = collate_samples(batch_items)
            labels = torch.as_tensor(batch["label"], device=device)
            batch_tensors = {key: torch.as_tensor(value, device=device) if key != "sample_id" and key != "split" else value for key, value in batch.items()}
            outputs = apply_modality_mask(batch_tensors, modalities)
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
            probs = torch.softmax(logits, dim=-1)
            pred = torch.argmax(probs, dim=-1)
            conf = torch.max(probs, dim=-1).values

            pred_np = pred.cpu().numpy()
            true_np = labels.cpu().numpy()
            y_true.append(true_np)
            y_pred.append(pred_np)

            for i in range(len(true_np)):
                rows.append(
                    {
                        "sample_id": batch["sample_id"][i],
                        "split": batch["split"][i],
                        "actual_label": int(true_np[i]),
                        "predicted_label": int(pred_np[i]),
                        "confidence": float(conf[i].cpu().item()),
                        "correct": bool(int(true_np[i]) == int(pred_np[i])),
                    }
                )

    if args.max_rows and args.max_rows > 0:
        rows = rows[: args.max_rows]

    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["sample_id", "split", "actual_label", "predicted_label", "confidence", "correct"],
        )
        writer.writeheader()
        writer.writerows(rows)

    y_true_arr = np.concatenate(y_true) if y_true else np.array([], dtype=np.int64)
    y_pred_arr = np.concatenate(y_pred) if y_pred else np.array([], dtype=np.int64)
    metrics = {
        "accuracy": accuracy_score(y_true_arr, y_pred_arr),
        "macro_f1": macro_f1_score(y_true_arr, y_pred_arr, model_cfg.num_classes),
        "weighted_f1": weighted_f1_score(y_true_arr, y_pred_arr, model_cfg.num_classes),
        "num_samples": int(len(y_true_arr)),
        "output_csv": str(out_path),
    }
    print(metrics)
    print(f"Wrote per-sample predictions to {out_path}")


if __name__ == "__main__":
    main()
