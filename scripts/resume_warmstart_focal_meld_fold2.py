from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader

try:
    from transformers import AutoTokenizer
except Exception:  # pragma: no cover
    AutoTokenizer = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import ManifestDataset, collate_samples, load_manifest, normalize_text
from src.metrics import accuracy_score, macro_f1_score, weighted_accuracy_score, weighted_f1_score, unweighted_accuracy_score
from src.models import LegalMemoCMTPhase1, ModelConfig, TrainConfig
from src.train.train import (
    apply_modality_mask,
    build_dataset,
    compute_class_weights,
    get_device,
    parse_encoder_mode,
    parse_modalities,
    parse_pooling,
)
from src.utils import ensure_dir, set_seed


def run_epoch(model, loader, optimizer, device, num_classes: int, loss_fn, modalities: set[str]):
    is_train = optimizer is not None
    model.train(is_train)
    all_true = []
    all_pred = []
    total_loss = 0.0
    seen = 0
    skipped = 0

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
        logits = torch.nan_to_num(logits, nan=0.0, posinf=0.0, neginf=0.0)
        loss = loss_fn(logits, labels)
        if torch.isnan(loss) or torch.isinf(loss):
            skipped += 1
            continue

        if is_train:
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        total_loss += float(loss.item()) * len(labels)
        seen += len(labels)
        pred = torch.argmax(logits, dim=-1).detach().cpu().numpy()
        all_pred.append(pred)
        all_true.append(labels.detach().cpu().numpy())

    y_true = np.concatenate(all_true) if all_true else np.array([], dtype=np.int64)
    y_pred = np.concatenate(all_pred) if all_pred else np.array([], dtype=np.int64)
    return {
        "loss": total_loss / max(seen, 1),
        "accuracy": accuracy_score(y_true, y_pred),
        "weighted_accuracy": weighted_accuracy_score(y_true, y_pred),
        "unweighted_accuracy": unweighted_accuracy_score(y_true, y_pred, num_classes),
        "macro_f1": macro_f1_score(y_true, y_pred, num_classes),
        "weighted_f1": weighted_f1_score(y_true, y_pred, num_classes),
        "skipped_batches": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume Fold 2 from warm-start weighted-CE checkpoint and continue with focal loss")
    parser.add_argument("--train-manifest", type=str, default="data/manifests/meld_cv/meld_fold_2_train.csv")
    parser.add_argument("--val-manifest", type=str, default="data/manifests/meld_cv/meld_fold_2_val.csv")
    parser.add_argument(
        "--base-checkpoint",
        type=str,
        default="results/improvement/warmstart_focal/meld_selected/cmt_min/fold_2/base_weighted_ce_checkpoint.pt",
        help="Checkpoint to resume from",
    )
    parser.add_argument("--output-dir", type=str, default="results/improvement/warmresume_focal/meld_fold_2")
    parser.add_argument("--epochs", type=int, default=2, help="Extra epochs to continue training")
    parser.add_argument("--lr", type=float, default=5e-5, help="Smaller learning rate for the resume stage")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--modalities", type=str, default="text,audio")
    parser.add_argument("--fusion-pooling", type=str, default="min", choices=["cls", "mean", "max", "min"])
    parser.add_argument("--encoder-mode", type=str, default="paper", choices=["legacy", "pretrained", "paper"])
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--checkpoint-manifest", type=str, default="data/manifests/meld_raw.csv", help="Manifest used for final test evaluation")
    parser.add_argument("--output-json", type=str, default="")
    parser.add_argument("--output-predictions-csv", type=str, default="")
    args = parser.parse_args()

    base_ckpt = Path(args.base_checkpoint)
    if not base_ckpt.exists():
        raise FileNotFoundError(f"Missing base checkpoint: {base_ckpt}")

    train_cfg = TrainConfig(seed=args.seed, batch_size=args.batch_size, epochs=args.epochs, lr=args.lr, output_dir=args.output_dir)
    train_cfg.device = args.device
    model_cfg = ModelConfig(fusion_pooling=parse_pooling(args.fusion_pooling), encoder_mode=parse_encoder_mode(args.encoder_mode))
    model_cfg.freeze_text_backbone = False
    model_cfg.freeze_audio_backbone = False

    set_seed(train_cfg.seed)
    device = get_device(train_cfg.device)
    ensure_dir(train_cfg.output_dir)

    train_samples = load_manifest(args.train_manifest)
    val_samples = load_manifest(args.val_manifest)
    modalities = parse_modalities(args.modalities)
    model_cfg.use_video = "video" in modalities
    train_ds = build_dataset(train_samples, model_cfg, modalities)
    val_ds = build_dataset(val_samples, model_cfg, modalities)

    train_loader = DataLoader(train_ds, batch_size=train_cfg.batch_size, shuffle=True, collate_fn=collate_samples)
    val_loader = DataLoader(val_ds, batch_size=train_cfg.batch_size, shuffle=False, collate_fn=collate_samples)

    checkpoint = torch.load(base_ckpt, map_location="cpu")
    if "model_cfg" in checkpoint:
        loaded_cfg = checkpoint["model_cfg"]
        # Keep the paper branch and pooling choice from the resume script.
        loaded_cfg["encoder_mode"] = parse_encoder_mode(args.encoder_mode)
        loaded_cfg["fusion_pooling"] = parse_pooling(args.fusion_pooling)
        model_cfg = ModelConfig(**loaded_cfg)
        model_cfg.freeze_text_backbone = False
        model_cfg.freeze_audio_backbone = False
        model_cfg.use_video = "video" in modalities

    model = LegalMemoCMTPhase1(model_cfg).to(device)
    model.load_state_dict(checkpoint["model_state"])

    optimizer = torch.optim.AdamW(model.parameters(), lr=train_cfg.lr, weight_decay=train_cfg.weight_decay)
    class_weights = compute_class_weights(train_ds, model_cfg.num_classes).to(device)
    loss_fn = FocalLoss(gamma=args.focal_gamma, weight=class_weights)

    best_val = -1.0
    best_path = f"{train_cfg.output_dir}/best_model.pt"

    for epoch in range(1, train_cfg.epochs + 1):
        train_metrics = run_epoch(model, train_loader, optimizer, device, model_cfg.num_classes, loss_fn, modalities)
        with torch.no_grad():
            val_metrics = run_epoch(model, val_loader, None, device, model_cfg.num_classes, loss_fn, modalities)
        msg = [
            f"epoch={epoch}",
            f"train_loss={train_metrics['loss']:.4f}",
            f"train_acc={train_metrics['accuracy']:.4f}",
            f"val_loss={val_metrics['loss']:.4f}",
            f"val_acc={val_metrics['accuracy']:.4f}",
        ]
        print(" | ".join(msg))
        if val_metrics["accuracy"] > best_val:
            best_val = val_metrics["accuracy"]
            torch.save({"model_state": model.state_dict(), "model_cfg": asdict(model_cfg), "train_cfg": asdict(train_cfg)}, best_path)

    # Final test evaluation using the same result style as the earlier scripts.
    from src.train.evaluate import main as evaluate_main  # local import to avoid script-side side effects

    # Reuse the evaluation entrypoint by simulating CLI via a temporary argv.
    import sys

    output_json = args.output_json or f"{train_cfg.output_dir}/metrics.json"
    output_predictions_csv = args.output_predictions_csv or f"{train_cfg.output_dir}/predictions_test.csv"
    old_argv = sys.argv[:]
    try:
        sys.argv = [
            "evaluate",
            "--manifest",
            args.checkpoint_manifest,
            "--split",
            "test",
            "--checkpoint",
            best_path,
            "--output-json",
            output_json,
            "--output-predictions-csv",
            output_predictions_csv,
            "--encoder-mode",
            args.encoder_mode,
            "--device",
            args.device,
            "--modalities",
            args.modalities,
            "--fusion-pooling",
            args.fusion_pooling,
            "--batch-size",
            str(args.batch_size),
        ]
        evaluate_main()
    finally:
        sys.argv = old_argv


class FocalLoss(nn.Module):
    def __init__(self, gamma: float = 2.0, weight: torch.Tensor | None = None) -> None:
        super().__init__()
        self.gamma = gamma
        self.register_buffer("weight", weight if weight is not None else None, persistent=False)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce = F.cross_entropy(logits, targets, weight=self.weight, reduction="none")
        pt = torch.exp(-ce)
        loss = ((1 - pt) ** self.gamma) * ce
        return loss.mean()


if __name__ == "__main__":
    main()
