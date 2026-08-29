from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import fields
from pathlib import Path

# The Phase 1 checkpoint uses Hugging Face PyTorch models. TensorFlow is not
# needed for inference and can crash during transformers import on macOS.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

import torch
import numpy as np
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data import collate_samples, load_manifest  # noqa: E402
from src.models import LegalMemoCMTPhase1, ModelConfig  # noqa: E402
from src.train.train import build_dataset, get_device, parse_modalities  # noqa: E402


LABELS = ["neutral", "anger", "disgust", "fear", "joy", "sadness", "surprise"]


def load_checkpoint(path: Path) -> tuple[LegalMemoCMTPhase1, dict[str, object]]:
    checkpoint = torch.load(path, map_location="cpu")
    raw_cfg = checkpoint.get("model_cfg", {}) if isinstance(checkpoint, dict) else {}
    allowed = {field.name for field in fields(ModelConfig)}
    cfg = ModelConfig(**{key: value for key, value in raw_cfg.items() if key in allowed})
    if cfg.num_classes != len(LABELS):
        raise ValueError(f"Expected a seven-class MELD checkpoint, found num_classes={cfg.num_classes}")
    model = LegalMemoCMTPhase1(cfg)
    state = checkpoint.get("model_state", checkpoint) if isinstance(checkpoint, dict) else checkpoint
    missing, unexpected = model.load_state_dict(state, strict=False)
    allowed_unused = {
        key for key in missing
        if key.startswith("gated_fusion.") or key.startswith("video_aux_classifier.")
    }
    unexpected = list(unexpected)
    if unexpected or set(missing) - allowed_unused:
        raise ValueError(
            "Checkpoint mismatch: "
            f"missing={sorted(set(missing) - allowed_unused)} unexpected={unexpected}"
        )
    model.eval()
    return model, {"model_cfg": raw_cfg}


def entropy(probabilities: list[float]) -> float:
    return -sum(p * math.log(max(p, 1e-12)) for p in probabilities)


def predict_batch(model, batch: dict[str, object], device: torch.device, modalities: set[str], encoder_mode: str):
    tensors = {
        "text_input_ids": torch.as_tensor(batch["text_input_ids"], device=device) if "text_input_ids" in batch else None,
        "text_attention_mask": torch.as_tensor(batch["text_attention_mask"], device=device) if "text_attention_mask" in batch else None,
        "audio_waveform": torch.as_tensor(batch["audio_waveform"], device=device) if "audio_waveform" in batch else None,
        "audio_attention_mask": torch.as_tensor(batch["audio_attention_mask"], device=device) if "audio_attention_mask" in batch else None,
        "video_features": torch.as_tensor(batch["video_features"], device=device),
        "video_mask": torch.as_tensor(batch["video_mask"], device=device),
        "text_tokens": torch.as_tensor(batch["text_tokens"], device=device) if "text_tokens" in batch else None,
        "audio_features": torch.as_tensor(batch["audio_features"], device=device) if "audio_features" in batch else None,
        "audio_mask": torch.as_tensor(batch["audio_mask"], device=device) if "audio_mask" in batch else None,
    }
    if encoder_mode in {"paper", "pretrained"}:
        if "text" not in modalities:
            tensors["text_input_ids"] = tensors["text_attention_mask"] = None
        if "audio" not in modalities:
            tensors["audio_waveform"] = tensors["audio_attention_mask"] = None
        if "video" not in modalities:
            tensors["video_features"] = tensors["video_mask"] = None
    else:
        if "text" not in modalities:
            tensors["text_tokens"] = None
        if "audio" not in modalities:
            tensors["audio_features"] = tensors["audio_mask"] = None
        if "video" not in modalities:
            tensors["video_features"] = tensors["video_mask"] = None
    logits = model(**tensors)
    return torch.softmax(logits, dim=-1).detach().cpu()


def main() -> None:
    parser = argparse.ArgumentParser(description="Add provenance-preserving Phase 1 MELD pseudo-labels to a Clancy manifest")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--max-rows", type=int, default=0, help="0 means all rows; use 100-300 for the smoke pilot")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--modalities", default="text,audio,video")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_path = Path(args.output_csv)
    checkpoint_path = Path(args.checkpoint)
    rows = list(csv.DictReader(input_path.open(newline="", encoding="utf-8")))
    if args.max_rows > 0:
        rows = rows[: args.max_rows]
    if not rows:
        raise SystemExit("No rows selected")
    samples = load_manifest(input_path)
    if args.max_rows > 0:
        samples = samples[: args.max_rows]

    model, checkpoint_meta = load_checkpoint(checkpoint_path)
    model_cfg = model.config
    modalities = parse_modalities(args.modalities)
    effective_modalities = set(modalities)
    if "video" in effective_modalities and not model_cfg.use_video:
        print(
            "WARNING: checkpoint model_cfg.use_video=false; video will not be consumed "
            "by this Phase 1 model. Recording effective modalities as text,audio.",
            file=sys.stderr,
        )
        effective_modalities.remove("video")
    if not effective_modalities:
        raise ValueError("No modalities remain after applying checkpoint capabilities")
    if "video" in effective_modalities and model_cfg.encoder_mode in {"pretrained", "paper"}:
        missing_features = [
            str(sample.sample_id)
            for sample in samples
            if not sample.video_features_path or not Path(sample.video_features_path).exists()
        ]
        if missing_features:
            raise ValueError(
                "Trimodal paper-checkpoint inference requires an existing video_features_path "
                f"(.npy ViT features) for every selected row; missing={len(missing_features)}. "
                "Run build_clancy_vit_facecrop_embeddings.py first and use its output manifest."
            )
        first_feature = np.load(samples[0].video_features_path, allow_pickle=False, mmap_mode="r")
        if first_feature.ndim != 2 or first_feature.shape[1] != model_cfg.video_dim:
            raise ValueError(
                "Video feature dimension mismatch: "
                f"found={getattr(first_feature, 'shape', None)} expected=(*, {model_cfg.video_dim}). "
                "Use 768-dimensional ViT features for this checkpoint."
            )
    # Accept both the documented GPU shorthand ("0") and the explicit
    # PyTorch form ("cuda:0"). Bare integers are invalid torch devices.
    device_arg = f"cuda:{args.device}" if str(args.device).isdigit() else args.device
    device = get_device(device_arg)
    model.to(device)
    dataset = build_dataset(samples, model_cfg, effective_modalities)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, collate_fn=collate_samples)

    predictions: dict[str, dict[str, object]] = {}
    with torch.no_grad():
        for batch in loader:
            probabilities = predict_batch(model, batch, device, effective_modalities, model_cfg.encoder_mode)
            for sample_id, vector in zip(batch["sample_id"], probabilities.tolist()):
                best_index = max(range(len(vector)), key=vector.__getitem__)
                predictions[str(sample_id)] = {
                    "phase1_basic_emotion": LABELS[best_index],
                    "phase1_basic_emotion_confidence": round(float(vector[best_index]), 6),
                    "phase1_basic_emotion_entropy": round(entropy(vector), 6),
                    "phase1_basic_emotion_probabilities": json.dumps({label: round(float(vector[i]), 6) for i, label in enumerate(LABELS)}, sort_keys=True),
                }

    output_rows = []
    for row in rows:
        sample_id = row.get("utterance_id") or row.get("turn_id") or ""
        prediction = predictions.get(sample_id)
        if prediction is None:
            raise ValueError(f"Missing prediction for {sample_id}")
        enriched = dict(row)
        enriched.update(prediction)
        enriched["phase1_basic_emotion_checkpoint"] = str(checkpoint_path)
        enriched["phase1_basic_emotion_source"] = "phase1_meld_checkpoint_pseudo_label"
        enriched["phase1_basic_emotion_modalities"] = ",".join(sorted(effective_modalities))
        enriched["phase1_basic_emotion_requested_modalities"] = ",".join(sorted(modalities))
        enriched["phase1_basic_emotion_model_config"] = json.dumps(checkpoint_meta["model_cfg"], sort_keys=True)
        output_rows.append(enriched)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(output_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(output_rows)

    confidence_values = [float(row["phase1_basic_emotion_confidence"]) for row in output_rows]
    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "checkpoint": str(checkpoint_path),
        "rows_processed": len(output_rows),
        "requested_modalities": sorted(modalities),
        "effective_modalities": sorted(effective_modalities),
        "device": str(device),
        "encoder_mode": model_cfg.encoder_mode,
        "label_vocabulary": LABELS,
        "prediction_counts": {label: sum(row["phase1_basic_emotion"] == label for row in output_rows) for label in LABELS},
        "confidence_mean": round(sum(confidence_values) / len(confidence_values), 6),
        "confidence_min": round(min(confidence_values), 6),
        "confidence_max": round(max(confidence_values), 6),
        "notes": [
            "Predictions are weak labels, not gold annotations.",
            "Original emotion_label fields were preserved unchanged.",
            "Courtroom-affect fields were not inferred.",
            (
                "Video was consumed by the selected checkpoint."
                if "video" in effective_modalities and model_cfg.use_video
                else "Video was not consumed by the selected checkpoint."
            ),
            "No deception, truthfulness, credibility, or reliability label was created.",
        ],
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
