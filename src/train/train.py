from __future__ import annotations

import argparse
from dataclasses import asdict

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, random_split

try:
    from transformers import AutoTokenizer
except Exception:  # pragma: no cover
    AutoTokenizer = None  # type: ignore[assignment]

from ..data import ManifestDataset, collate_samples, load_manifest
from ..metrics import accuracy_score, macro_f1_score, weighted_f1_score
from ..models import LegalMemoCMTPhase1, ModelConfig, TrainConfig
from ..utils import ensure_dir, set_seed


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


def parse_encoder_mode(value: str) -> str:
    value = value.strip().lower()
    return value if value in {"legacy", "pretrained", "paper"} else "legacy"


def compute_class_weights(train_subset, num_classes: int) -> torch.Tensor:
    if hasattr(train_subset, "indices"):
        labels = [train_subset.dataset.samples[i].label for i in train_subset.indices]
    else:
        labels = [s.label for s in train_subset.samples]
    counts = np.bincount(np.asarray(labels, dtype=np.int64), minlength=num_classes).astype(np.float32)
    counts = np.maximum(counts, 1.0)
    weights = counts.sum() / (num_classes * counts)
    return torch.tensor(weights, dtype=torch.float32)


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


def get_device(device: str) -> torch.device:
    if device == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(device)


def build_dataset(samples, model_cfg, modalities: set[str] | None = None):
    tokenizer = None
    if parse_encoder_mode(model_cfg.encoder_mode) in {"pretrained", "paper"}:
        if AutoTokenizer is None:
            raise ImportError("transformers is required for pretrained encoder mode")
        tokenizer = AutoTokenizer.from_pretrained(model_cfg.text_model_name, use_fast=False)
    load_video = True if modalities is None else "video" in modalities
    return ManifestDataset(
        samples,
        tokenizer=tokenizer,
        max_text_len=model_cfg.max_text_len,
        max_audio_len=model_cfg.max_audio_len,
        max_video_len=model_cfg.max_video_len,
        encoder_mode=model_cfg.encoder_mode,
        load_video=load_video,
    )


def apply_modality_mask(batch, modalities: set[str], encoder_mode: str):
    if parse_encoder_mode(encoder_mode) in {"pretrained", "paper"}:
        text_input_ids = batch["text_input_ids"]
        text_attention_mask = batch["text_attention_mask"]
        audio_waveform = batch["audio_waveform"]
        audio_attention_mask = batch["audio_attention_mask"]
        video_features = batch["video_features"]
        video_mask = batch["video_mask"]

        if "text" not in modalities:
            text_input_ids = None
            text_attention_mask = None
        if "audio" not in modalities:
            audio_waveform = None
            audio_attention_mask = None
        if "video" not in modalities:
            video_features = None
            video_mask = None
        return text_input_ids, text_attention_mask, audio_waveform, audio_attention_mask, video_features, video_mask

    text_tokens = batch["text_tokens"]
    audio_features = batch["audio_features"]
    audio_mask = batch["audio_mask"]
    video_features = batch["video_features"]
    video_mask = batch["video_mask"]

    if "text" not in modalities:
        text_tokens = None
    if "audio" not in modalities:
        audio_features = None
        audio_mask = None
    if "video" not in modalities:
        video_features = None
        video_mask = None
    return text_tokens, audio_features, audio_mask, video_features, video_mask


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


def main():
    parser = argparse.ArgumentParser(description="Train LegalMemoCMT Phase 1")
    parser.add_argument("--manifest", type=str, required=True, help="CSV manifest path")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--output-dir", type=str, default="results/phase1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--loss-type", type=str, default="ce", choices=["ce", "weighted-ce", "focal"])
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--modalities", type=str, default="text,audio,video", help="Comma-separated subset of text,audio,video")
    parser.add_argument("--fusion-pooling", type=str, default="mean", choices=["cls", "mean", "max", "min"])
    parser.add_argument("--encoder-mode", type=str, default="legacy", choices=["legacy", "pretrained", "paper"])
    parser.add_argument("--fine-tune-backbones", action="store_true", help="Update pretrained text/audio backbones instead of freezing them")
    parser.add_argument("--device", type=str, default="cpu", help="Training device: cpu, cuda, mps, or auto")
    parser.add_argument("--train-split", type=str, default="", help="Optional split filter for the training manifest")
    parser.add_argument("--val-manifest", type=str, default="", help="Optional separate validation manifest")
    parser.add_argument("--val-split", type=str, default="", help="Optional split filter for validation from the same manifest")
    args = parser.parse_args()

    train_cfg = TrainConfig(seed=args.seed, batch_size=args.batch_size, epochs=args.epochs, lr=args.lr, output_dir=args.output_dir)
    train_cfg.device = args.device
    model_cfg = ModelConfig(fusion_pooling=parse_pooling(args.fusion_pooling), encoder_mode=parse_encoder_mode(args.encoder_mode))
    if args.fine_tune_backbones:
        model_cfg.freeze_text_backbone = False
        model_cfg.freeze_audio_backbone = False

    set_seed(train_cfg.seed)
    device = get_device(train_cfg.device)
    ensure_dir(train_cfg.output_dir)

    samples = load_manifest(args.manifest)
    if args.train_split.strip():
        wanted_split = args.train_split.strip().lower()
        samples = [sample for sample in samples if sample.split.lower() == wanted_split]
        if not samples:
            raise ValueError(f"No samples found for train split '{wanted_split}' in {args.manifest}")
    modalities = parse_modalities(args.modalities)
    model_cfg.use_video = "video" in modalities
    dataset = build_dataset(samples, model_cfg, modalities)
    if args.val_manifest.strip():
        val_samples = load_manifest(args.val_manifest)
        val_ds = build_dataset(val_samples, model_cfg, modalities)
        train_ds = dataset
    elif args.val_split.strip():
        wanted_split = args.val_split.strip().lower()
        val_samples = [sample for sample in load_manifest(args.manifest) if sample.split.lower() == wanted_split]
        if not val_samples:
            raise ValueError(f"No samples found for val split '{wanted_split}' in {args.manifest}")
        val_ds = build_dataset(val_samples, model_cfg, modalities)
        train_ds = dataset
    else:
        n_total = len(dataset)
        n_train = max(int(0.8 * n_total), 1)
        n_val = max(n_total - n_train, 1) if n_total > 1 else 0
        if n_val > 0:
            train_ds, val_ds = random_split(dataset, [n_train, n_total - n_train], generator=torch.Generator().manual_seed(train_cfg.seed))
        else:
            train_ds, val_ds = dataset, None

    train_loader = DataLoader(train_ds, batch_size=train_cfg.batch_size, shuffle=True, collate_fn=collate_samples)
    val_loader = DataLoader(val_ds, batch_size=train_cfg.batch_size, shuffle=False, collate_fn=collate_samples) if val_ds is not None else None

    model = LegalMemoCMTPhase1(model_cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=train_cfg.lr, weight_decay=train_cfg.weight_decay)
    class_weights = compute_class_weights(train_ds, model_cfg.num_classes).to(device) if args.loss_type in {"weighted-ce", "focal"} else None
    if args.loss_type == "ce":
        loss_fn = nn.CrossEntropyLoss()
    elif args.loss_type == "weighted-ce":
        loss_fn = nn.CrossEntropyLoss(weight=class_weights)
    else:
        loss_fn = FocalLoss(gamma=args.focal_gamma, weight=class_weights)

    best_val = -1.0
    best_path = f"{train_cfg.output_dir}/best_model.pt"

    for epoch in range(1, train_cfg.epochs + 1):
        train_metrics = run_epoch(model, train_loader, optimizer, device, model_cfg.num_classes, loss_fn, modalities)
        msg = [f"epoch={epoch}", f"train_loss={train_metrics['loss']:.4f}", f"train_acc={train_metrics['accuracy']:.4f}"]

        if val_loader is not None:
            with torch.no_grad():
                val_metrics = run_epoch(model, val_loader, None, device, model_cfg.num_classes, loss_fn, modalities)
            msg += [f"val_loss={val_metrics['loss']:.4f}", f"val_acc={val_metrics['accuracy']:.4f}"]
            if val_metrics["accuracy"] > best_val:
                best_val = val_metrics["accuracy"]
                torch.save({"model_state": model.state_dict(), "model_cfg": asdict(model_cfg), "train_cfg": asdict(train_cfg)}, best_path)
        else:
            torch.save({"model_state": model.state_dict(), "model_cfg": asdict(model_cfg), "train_cfg": asdict(train_cfg)}, best_path)

        print(" | ".join(msg))


if __name__ == "__main__":
    main()
