from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, random_split

try:
    from transformers import AutoTokenizer
except Exception:  # pragma: no cover
    AutoTokenizer = None  # type: ignore[assignment]

from src.data import ManifestDataset, collate_samples, load_manifest
from src.metrics import accuracy_score, macro_f1_score, weighted_f1_score
from src.models import LegalMemoCMTPhase1, ModelConfig, TrainConfig
from src.train.train import FocalLoss, apply_modality_mask, build_dataset, compute_class_weights, get_device, parse_encoder_mode, parse_fusion_mode, parse_modalities, parse_pooling
from src.utils import ensure_dir, set_seed


def load_partial_checkpoint(model: nn.Module, checkpoint_path: Path, *, reset_head: bool = True) -> dict[str, object]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    state_dict = checkpoint.get("model_state", checkpoint)
    if reset_head:
        state_dict = {k: v for k, v in state_dict.items() if not k.startswith("classifier.")}
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    print(f"Loaded checkpoint from {checkpoint_path}")
    print(f"Missing keys: {len(missing)} | Unexpected keys: {len(unexpected)}")
    return checkpoint if isinstance(checkpoint, dict) else {}


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
        "macro_f1": macro_f1_score(y_true, y_pred, num_classes),
        "weighted_f1": weighted_f1_score(y_true, y_pred, num_classes),
        "skipped_batches": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune LegalMemoCMT from a MELD checkpoint for Phase 2")
    parser.add_argument("--manifest", type=str, required=True, help="Phase 2 labeled manifest CSV")
    parser.add_argument("--init-checkpoint", type=str, required=True, help="Checkpoint to warm-start from")
    parser.add_argument("--output-dir", type=str, required=True, help="Output directory for the new run")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--loss-type", type=str, default="weighted-ce", choices=["ce", "weighted-ce", "focal"])
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--modalities", type=str, default="text,audio", help="Comma-separated subset of text,audio,video")
    parser.add_argument("--fusion-pooling", type=str, default="mean", choices=["cls", "mean", "max", "min"])
    parser.add_argument("--fusion-mode", type=str, default="gated", choices=["legacy", "gated"])
    parser.add_argument("--encoder-mode", type=str, default="paper", choices=["legacy", "pretrained", "paper"])
    parser.add_argument("--num-classes", type=int, default=7)
    parser.add_argument("--fine-tune-backbones", action="store_true", help="Update pretrained text/audio backbones instead of freezing them")
    parser.add_argument("--reset-head", dest="reset_head", action="store_true", help="Discard classifier weights when loading the MELD checkpoint")
    parser.add_argument("--keep-head", dest="reset_head", action="store_false", help="Keep classifier weights when loading the checkpoint")
    parser.set_defaults(reset_head=True)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--train-split", type=str, default="train")
    parser.add_argument("--val-split", type=str, default="dev")
    parser.add_argument("--save-summary-json", type=str, default="")
    args = parser.parse_args()

    set_seed(args.seed)
    device = get_device(args.device)
    ensure_dir(Path(args.output_dir))

    model_cfg = ModelConfig(
        fusion_pooling=parse_pooling(args.fusion_pooling),
        fusion_mode=parse_fusion_mode(args.fusion_mode),
        encoder_mode=parse_encoder_mode(args.encoder_mode),
        num_classes=args.num_classes,
    )
    if args.fine_tune_backbones:
        model_cfg.freeze_text_backbone = False
        model_cfg.freeze_audio_backbone = False

    model = LegalMemoCMTPhase1(model_cfg).to(device)
    load_partial_checkpoint(model, Path(args.init_checkpoint), reset_head=args.reset_head)

    samples = load_manifest(args.manifest)
    if args.train_split.strip():
        train_samples = [sample for sample in samples if sample.split.lower() == args.train_split.strip().lower()]
    else:
        train_samples = samples
    if args.val_split.strip():
        val_samples = [sample for sample in samples if sample.split.lower() == args.val_split.strip().lower()]
    else:
        val_samples = []

    modalities = parse_modalities(args.modalities)
    model_cfg.use_video = "video" in modalities
    train_ds = build_dataset(train_samples, model_cfg, modalities)
    val_ds = build_dataset(val_samples, model_cfg, modalities) if val_samples else None
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=collate_samples)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collate_samples) if val_ds is not None else None

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-2)
    class_weights = compute_class_weights(train_ds, model_cfg.num_classes).to(device) if args.loss_type in {"weighted-ce", "focal"} else None
    if args.loss_type == "ce":
        loss_fn = nn.CrossEntropyLoss()
    elif args.loss_type == "weighted-ce":
        loss_fn = nn.CrossEntropyLoss(weight=class_weights)
    else:
        loss_fn = FocalLoss(gamma=args.focal_gamma, weight=class_weights)

    best_val = -1.0
    best_path = Path(args.output_dir) / "best_model.pt"
    history = []
    for epoch in range(1, args.epochs + 1):
        train_metrics = run_epoch(model, train_loader, optimizer, device, model_cfg.num_classes, loss_fn, modalities)
        msg = [f"epoch={epoch}", f"train_loss={train_metrics['loss']:.4f}", f"train_acc={train_metrics['accuracy']:.4f}"]
        record = {"epoch": epoch, "train": train_metrics}
        if val_loader is not None:
            with torch.no_grad():
                val_metrics = run_epoch(model, val_loader, None, device, model_cfg.num_classes, loss_fn, modalities)
            msg += [f"val_loss={val_metrics['loss']:.4f}", f"val_acc={val_metrics['accuracy']:.4f}"]
            record["val"] = val_metrics
            if val_metrics["accuracy"] > best_val:
                best_val = val_metrics["accuracy"]
                torch.save({"model_state": model.state_dict(), "model_cfg": asdict(model_cfg), "train_cfg": asdict(TrainConfig(seed=args.seed, batch_size=args.batch_size, epochs=args.epochs, lr=args.lr, output_dir=args.output_dir))}, best_path)
        else:
            torch.save({"model_state": model.state_dict(), "model_cfg": asdict(model_cfg), "train_cfg": asdict(TrainConfig(seed=args.seed, batch_size=args.batch_size, epochs=args.epochs, lr=args.lr, output_dir=args.output_dir))}, best_path)
        print(" | ".join(msg))
        history.append(record)

    if args.save_summary_json:
        summary = {
            "best_val_accuracy": best_val,
            "history": history,
            "init_checkpoint": args.init_checkpoint,
            "modalities": sorted(list(modalities)),
            "num_classes": args.num_classes,
        }
        Path(args.save_summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
