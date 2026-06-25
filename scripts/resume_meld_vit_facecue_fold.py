from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import load_manifest
from src.data import collate_samples
from src.metrics import accuracy_score, macro_f1_score, weighted_accuracy_score, weighted_f1_score, unweighted_accuracy_score
from src.models import LegalMemoCMTPhase1, ModelConfig, TrainConfig
from src.train.train import (
    apply_modality_mask,
    build_dataset,
    compute_class_weights,
    get_device,
    parse_fusion_mode,
    parse_encoder_mode,
    parse_modalities,
    parse_pooling,
    run_epoch,
)
from src.utils import ensure_dir, set_seed


def set_requires_grad(module: nn.Module, enabled: bool) -> None:
    for param in module.parameters():
        param.requires_grad = enabled


def infer_video_dim(manifest_csv: Path) -> int:
    samples = load_manifest(manifest_csv)
    for sample in samples:
        video_path = Path(sample.video_path)
        if video_path.exists() and video_path.suffix.lower() == ".npy":
            arr = np.load(video_path, allow_pickle=False, mmap_mode="r")
            if arr.ndim == 1:
                return int(arr.shape[0])
            return int(arr.shape[-1])
    return 768


def load_checkpoint_with_video_shape(checkpoint_path: Path, model: LegalMemoCMTPhase1) -> dict:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    state = checkpoint["model_state"]
    filtered = {k: v for k, v in state.items() if not k.startswith("video_encoder.")}
    missing, unexpected = model.load_state_dict(filtered, strict=False)
    print(f"Loaded checkpoint from {checkpoint_path}")
    if missing:
        print(f"Missing keys after warm-start: {sorted(missing)}")
    if unexpected:
        print(f"Unexpected keys after warm-start: {sorted(unexpected)}")
    return checkpoint


def build_metrics(loss: float, y_true: np.ndarray, y_pred: np.ndarray, num_classes: int, skipped: int) -> dict:
    return {
        "loss": loss,
        "accuracy": accuracy_score(y_true, y_pred),
        "weighted_accuracy": weighted_accuracy_score(y_true, y_pred),
        "unweighted_accuracy": unweighted_accuracy_score(y_true, y_pred, num_classes),
        "macro_f1": macro_f1_score(y_true, y_pred, num_classes),
        "weighted_f1": weighted_f1_score(y_true, y_pred, num_classes),
        "skipped_batches": skipped,
    }


def selection_score(metrics: dict, metric_name: str) -> float:
    metric_name = metric_name.strip().lower()
    if metric_name not in {"accuracy", "weighted_f1", "macro_f1"}:
        raise ValueError(f"Unsupported selection metric: {metric_name}")
    value = metrics.get(metric_name)
    if value is None:
        raise KeyError(f"Metric '{metric_name}' not found in metrics: {sorted(metrics)}")
    return float(value)


def train_one_epoch(model, loader, optimizer, device, num_classes: int, loss_fn, modalities: set[str]):
    return run_epoch(model, loader, optimizer, device, num_classes, loss_fn, modalities)


def run_epoch_with_video_aux(
    model,
    loader,
    optimizer,
    device,
    num_classes: int,
    main_loss_fn,
    aux_loss_fn,
    modalities: set[str],
    aux_weight: float,
):
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
            logits, video_aux_logits = model(
                text_input_ids=text_input_ids,
                text_attention_mask=text_attention_mask,
                audio_waveform=audio_waveform,
                audio_attention_mask=audio_attention_mask,
                video_features=video_features,
                video_mask=video_mask,
                return_video_aux=True,
            )
        else:
            text_tokens, audio_features, audio_mask, video_features, video_mask = outputs
            logits, video_aux_logits = model(
                text_tokens=text_tokens,
                audio_features=audio_features,
                audio_mask=audio_mask,
                video_features=video_features,
                video_mask=video_mask,
                return_video_aux=True,
            )

        logits = torch.nan_to_num(logits, nan=0.0, posinf=0.0, neginf=0.0)
        video_aux_logits = torch.nan_to_num(video_aux_logits, nan=0.0, posinf=0.0, neginf=0.0)
        main_loss = main_loss_fn(logits, labels)
        aux_loss = aux_loss_fn(video_aux_logits, labels)
        loss = main_loss + (aux_weight * aux_loss)

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
    parser = argparse.ArgumentParser(description="Warm-start MELD facial-cue training from the weighted-CE baseline")
    parser.add_argument("--fold", type=int, default=2, choices=[2, 4], help="MELD CV fold to fine-tune")
    parser.add_argument(
        "--manifest-dir",
        type=str,
        default="data/manifests/meld_vit_facecue_cv",
        help="Directory containing the facial-cue MELD fold CSV files",
    )
    parser.add_argument(
        "--raw-manifest",
        type=str,
        default="data/manifests/meld_vit_facecue.csv",
        help="Raw facial-cue manifest used for final test evaluation",
    )
    parser.add_argument(
        "--baseline-dir",
        type=str,
        default="results/paper_aligned_meld_cv/cmt_min",
        help="Directory containing the weighted-CE MELD checkpoint to warm-start from",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default="results/facial_cues/meld_vit",
        help="Root output directory for the facial-cue experiment",
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--freeze-backbone-epochs", type=int, default=1)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--modalities", type=str, default="text,audio,video")
    parser.add_argument("--fusion-pooling", type=str, default="min", choices=["cls", "mean", "max", "min"])
    parser.add_argument("--fusion-mode", type=str, default="legacy", choices=["legacy", "gated"])
    parser.add_argument("--encoder-mode", type=str, default="paper", choices=["legacy", "pretrained", "paper"])
    parser.add_argument("--video-aux-weight", type=float, default=0.0, help="Weight for the auxiliary video classification loss")
    parser.add_argument(
        "--video-aux-loss-type",
        type=str,
        default="weighted-ce",
        choices=["ce", "weighted-ce"],
        help="Loss used for the auxiliary video head",
    )
    parser.add_argument(
        "--early-stop-patience",
        type=int,
        default=0,
        help="Stop after this many epochs without improvement in the selection metric; 0 disables early stopping",
    )
    parser.add_argument(
        "--selection-metric",
        type=str,
        default="weighted_f1",
        choices=["accuracy", "weighted_f1", "macro_f1"],
        help="Validation metric used to decide which checkpoint is best",
    )
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader worker count")
    parser.add_argument("--pin-memory", action="store_true", help="Enable DataLoader pinned memory")
    parser.add_argument(
        "--persistent-workers",
        action="store_true",
        help="Keep DataLoader workers alive between epochs when num_workers > 0",
    )
    parser.add_argument("--video-dim", type=int, default=0, help="Override ViT embedding dim; 0 means infer from the manifest")
    args = parser.parse_args()

    baseline_dir = Path(args.baseline_dir)
    base_ckpt = baseline_dir / f"fold_{args.fold}" / "best_model.pt"
    if not base_ckpt.exists():
        raise FileNotFoundError(f"Missing baseline checkpoint: {base_ckpt}")

    train_manifest = Path(args.manifest_dir) / f"meld_fold_{args.fold}_train.csv"
    val_manifest = Path(args.manifest_dir) / f"meld_fold_{args.fold}_val.csv"
    raw_manifest = Path(args.raw_manifest)
    if not train_manifest.exists() or not val_manifest.exists():
        raise FileNotFoundError(f"Missing MELD facial-cue fold CSVs for fold {args.fold} in {args.manifest_dir}")
    if not raw_manifest.exists():
        raise FileNotFoundError(f"Missing raw facial-cue manifest: {raw_manifest}")

    output_dir = Path(args.output_root) / f"fold_{args.fold}"
    ensure_dir(output_dir)

    train_cfg = TrainConfig(seed=args.seed, batch_size=args.batch_size, epochs=args.epochs, lr=args.lr, output_dir=str(output_dir))
    train_cfg.device = args.device

    video_dim = args.video_dim or infer_video_dim(train_manifest)
    model_cfg = ModelConfig(
        encoder_mode=parse_encoder_mode(args.encoder_mode),
        fusion_mode=parse_fusion_mode(args.fusion_mode),
        fusion_pooling=parse_pooling(args.fusion_pooling),
        video_dim=int(video_dim),
    )
    model_cfg.freeze_text_backbone = False
    model_cfg.freeze_audio_backbone = False
    model_cfg.use_video = True

    set_seed(train_cfg.seed)
    device = get_device(train_cfg.device)

    train_samples = load_manifest(train_manifest)
    val_samples = load_manifest(val_manifest)
    modalities = parse_modalities(args.modalities)
    train_ds = build_dataset(train_samples, model_cfg, modalities)
    val_ds = build_dataset(val_samples, model_cfg, modalities)
    loader_kwargs = {
        "num_workers": max(0, int(args.num_workers)),
        "pin_memory": bool(args.pin_memory),
    }
    if loader_kwargs["num_workers"] > 0:
        loader_kwargs["persistent_workers"] = bool(args.persistent_workers)
    train_loader = DataLoader(
        train_ds,
        batch_size=train_cfg.batch_size,
        shuffle=True,
        collate_fn=collate_samples,
        **loader_kwargs,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=train_cfg.batch_size,
        shuffle=False,
        collate_fn=collate_samples,
        **loader_kwargs,
    )

    model = LegalMemoCMTPhase1(model_cfg).to(device)
    checkpoint = load_checkpoint_with_video_shape(base_ckpt, model)

    optimizer = torch.optim.AdamW(model.parameters(), lr=train_cfg.lr, weight_decay=train_cfg.weight_decay)
    class_weights = compute_class_weights(train_ds, model_cfg.num_classes).to(device)
    loss_fn = nn.CrossEntropyLoss(weight=class_weights)
    if args.video_aux_loss_type == "ce":
        video_aux_loss_fn = nn.CrossEntropyLoss()
    else:
        video_aux_loss_fn = nn.CrossEntropyLoss(weight=class_weights)

    best_val = -1.0
    epochs_without_improvement = 0
    best_path = output_dir / "best_model.pt"

    for epoch in range(1, train_cfg.epochs + 1):
        if args.freeze_backbone_epochs > 0 and epoch <= args.freeze_backbone_epochs:
            set_requires_grad(model.text_encoder, False)
            set_requires_grad(model.audio_encoder, False)
        else:
            set_requires_grad(model.text_encoder, True)
            set_requires_grad(model.audio_encoder, True)
        set_requires_grad(model.video_encoder, True)
        set_requires_grad(model.legacy_fusion, True)
        set_requires_grad(model.paper_fusion, True)
        set_requires_grad(model.classifier, True)

        if args.video_aux_weight > 0:
            train_metrics = run_epoch_with_video_aux(
                model,
                train_loader,
                optimizer,
                device,
                model_cfg.num_classes,
                loss_fn,
                video_aux_loss_fn,
                modalities,
                args.video_aux_weight,
            )
        else:
            train_metrics = train_one_epoch(model, train_loader, optimizer, device, model_cfg.num_classes, loss_fn, modalities)
        with torch.no_grad():
            if args.video_aux_weight > 0:
                val_metrics = run_epoch_with_video_aux(
                    model,
                    val_loader,
                    None,
                    device,
                    model_cfg.num_classes,
                    loss_fn,
                    video_aux_loss_fn,
                    modalities,
                    args.video_aux_weight,
                )
            else:
                val_metrics = run_epoch(model, val_loader, None, device, model_cfg.num_classes, loss_fn, modalities)

        print(
            " | ".join(
                [
                    f"epoch={epoch}",
                    f"train_loss={train_metrics['loss']:.4f}",
                    f"train_acc={train_metrics['accuracy']:.4f}",
                    f"val_loss={val_metrics['loss']:.4f}",
                    f"val_acc={val_metrics['accuracy']:.4f}",
                    f"val_{args.selection_metric}={selection_score(val_metrics, args.selection_metric):.4f}",
                ]
            )
        )
        current_score = selection_score(val_metrics, args.selection_metric)
        if current_score > best_val:
            best_val = current_score
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "model_cfg": asdict(model_cfg),
                    "train_cfg": asdict(train_cfg),
                    "selection_metric": args.selection_metric,
                    "selection_score": best_val,
                },
                best_path,
            )
        else:
            epochs_without_improvement += 1

        if args.early_stop_patience > 0 and epochs_without_improvement >= args.early_stop_patience:
            print(
                f"Early stopping triggered after {epoch} epochs without improvement in val_{args.selection_metric}."
            )
            break

    from src.train.evaluate import main as evaluate_main

    output_json = output_dir / "metrics.json"
    output_predictions_csv = output_dir / "predictions_test.csv"
    old_argv = sys.argv[:]
    try:
        sys.argv = [
            "evaluate",
            "--manifest",
            str(raw_manifest),
            "--split",
            "test",
            "--checkpoint",
            str(best_path),
            "--output-json",
            str(output_json),
            "--output-predictions-csv",
            str(output_predictions_csv),
            "--encoder-mode",
            args.encoder_mode,
            "--device",
            args.device,
            "--modalities",
            args.modalities,
            "--fusion-pooling",
            args.fusion_pooling,
            "--fusion-mode",
            args.fusion_mode,
            "--batch-size",
            str(args.batch_size),
        ]
        evaluate_main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
