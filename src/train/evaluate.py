from __future__ import annotations

import argparse
import json
import csv
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

try:
    from transformers import AutoTokenizer
except Exception:  # pragma: no cover
    AutoTokenizer = None  # type: ignore[assignment]

from ..data import ManifestDataset, collate_samples, load_manifest
from ..metrics import accuracy_score, macro_f1_score, unweighted_accuracy_score, weighted_accuracy_score, weighted_f1_score
from ..models import LegalMemoCMTPhase1, ModelConfig
from .train import apply_modality_mask, build_dataset, parse_encoder_mode, parse_fusion_mode, parse_modalities, parse_pooling


def main():
    parser = argparse.ArgumentParser(description="Evaluate LegalMemoCMT Phase 1")
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--output-json", type=str, default="", help="Optional path to save metrics as JSON")
    parser.add_argument("--output-predictions-csv", type=str, default="", help="Optional path to save per-sample predictions as CSV")
    parser.add_argument("--split", type=str, default="", help="Optional manifest split filter (e.g. train, dev, test)")
    parser.add_argument("--modalities", type=str, default="text,audio,video", help="Comma-separated subset of text,audio,video")
    parser.add_argument("--fusion-pooling", type=str, default="mean", choices=["cls", "mean", "max", "min"])
    parser.add_argument("--fusion-mode", type=str, default="", help="Optional override: legacy, gated")
    parser.add_argument("--encoder-mode", type=str, default="legacy", choices=["legacy", "pretrained", "paper"])
    parser.add_argument("--device", type=str, default="cpu", help="Evaluation device: cpu, cuda, mps, or auto")
    args = parser.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu")
    loaded_cfg = checkpoint.get("model_cfg", {})
    loaded_cfg["fusion_pooling"] = parse_pooling(args.fusion_pooling or loaded_cfg.get("fusion_pooling", "mean"))
    loaded_cfg["fusion_mode"] = parse_fusion_mode(args.fusion_mode or loaded_cfg.get("fusion_mode", "legacy"))
    loaded_cfg["encoder_mode"] = parse_encoder_mode(args.encoder_mode or loaded_cfg.get("encoder_mode", "legacy"))
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
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, collate_fn=collate_samples)

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"))
    else:
        device = torch.device(args.device)
    model = LegalMemoCMTPhase1(model_cfg).to(device)
    missing, unexpected = model.load_state_dict(checkpoint["model_state"], strict=False)
    if missing:
        print(f"Missing keys during evaluation load: {sorted(missing)}")
    if unexpected:
        print(f"Unexpected keys during evaluation load: {sorted(unexpected)}")
    model.eval()

    all_true = []
    all_pred = []
    rows: list[dict[str, object]] = []
    with torch.no_grad():
        for batch in loader:
            labels = torch.as_tensor(batch["label"], device=device)
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
            probs = torch.softmax(logits, dim=-1)
            pred = torch.argmax(probs, dim=-1).cpu().numpy()
            conf = torch.max(probs, dim=-1).values.cpu().numpy()
            all_pred.append(pred)
            all_true.append(labels.cpu().numpy())
            for i in range(len(pred)):
                rows.append(
                    {
                        "sample_id": batch["sample_id"][i],
                        "split": batch["split"][i],
                        "actual_label": int(labels.cpu().numpy()[i]),
                        "predicted_label": int(pred[i]),
                        "confidence": float(conf[i]),
                        "correct": bool(int(labels.cpu().numpy()[i]) == int(pred[i])),
                    }
                )

    y_true = np.concatenate(all_true)
    y_pred = np.concatenate(all_pred)
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "weighted_accuracy": weighted_accuracy_score(y_true, y_pred),
        "unweighted_accuracy": unweighted_accuracy_score(y_true, y_pred, model_cfg.num_classes),
        "macro_f1": macro_f1_score(y_true, y_pred, model_cfg.num_classes),
        "weighted_f1": weighted_f1_score(y_true, y_pred, model_cfg.num_classes),
        "num_samples": int(len(y_true)),
    }
    print(metrics)

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Wrote metrics JSON to {out}")

    if args.output_predictions_csv:
        out = Path(args.output_predictions_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["sample_id", "split", "actual_label", "predicted_label", "confidence", "correct"],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote per-sample predictions to {out}")


if __name__ == "__main__":
    main()
