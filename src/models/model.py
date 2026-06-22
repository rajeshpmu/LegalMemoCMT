from __future__ import annotations

import math

import torch
from torch import nn

try:
    from transformers import AutoModel
except Exception:  # pragma: no cover
    AutoModel = None  # type: ignore[assignment]

from .config import ModelConfig


class PositionalEncoding(nn.Module):
    def __init__(self, dim: int, dropout: float = 0.1, max_len: int = 5000) -> None:
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        pe = torch.zeros(max_len, dim)
        position = torch.arange(0, max_len, dtype=torch.float32).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, dim, 2, dtype=torch.float32) * (-math.log(10000.0) / dim))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0), persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        x = x + self.pe[:, : x.size(1)]
        return self.dropout(x)


class SequenceEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, num_layers: int, num_heads: int, dropout: float) -> None:
        super().__init__()
        self.proj = nn.Linear(input_dim, hidden_dim)
        self.pos = PositionalEncoding(hidden_dim, dropout=dropout)
        layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
            norm_first=False,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers, enable_nested_tensor=False)
        self.output_norm = nn.LayerNorm(hidden_dim)

    def forward(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
        x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        x = self.proj(x)
        x = self.pos(x)
        # Avoid MPS nested-tensor mask conversion; a plain encoder pass with
        # masked pooling is stable for this project.
        x = self.encoder(x)
        x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        if mask is None:
            pooled = x.mean(dim=1)
        else:
            valid = mask.bool().unsqueeze(-1)
            summed = (x * valid).sum(dim=1)
            denom = valid.sum(dim=1).clamp(min=1)
            pooled = summed / denom
        return self.output_norm(pooled)


class TextEncoder(nn.Module):
    def __init__(self, vocab_size: int, embed_dim: int, hidden_dim: int, num_layers: int, num_heads: int, dropout: float) -> None:
        super().__init__()
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.proj = nn.Linear(embed_dim, hidden_dim)
        self.pos = PositionalEncoding(hidden_dim, dropout=dropout)
        layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
            norm_first=False,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers, enable_nested_tensor=False)
        self.output_norm = nn.LayerNorm(hidden_dim)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        tokens = tokens.long().clamp(min=0, max=self.embed.num_embeddings - 1)
        x = self.embed(tokens)
        x = self.proj(x)
        x = self.pos(x)
        mask = tokens.ne(0)
        x = self.encoder(x)
        x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        valid = mask.unsqueeze(-1)
        summed = (x * valid).sum(dim=1)
        denom = valid.sum(dim=1).clamp(min=1)
        pooled = summed / denom
        return self.output_norm(pooled)


class CrossModalFusion(nn.Module):
    def __init__(self, hidden_dim: int, num_heads: int, num_layers: int, dropout: float, pooling: str = "mean") -> None:
        super().__init__()
        self.pooling = pooling.lower()
        self.modal_tokens = nn.Parameter(torch.randn(3, hidden_dim) * 0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
            norm_first=False,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers, enable_nested_tensor=False)
        self.output_norm = nn.LayerNorm(hidden_dim)

    def forward(self, text: torch.Tensor, audio: torch.Tensor, video: torch.Tensor) -> torch.Tensor:
        text = torch.nan_to_num(text, nan=0.0, posinf=0.0, neginf=0.0)
        audio = torch.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        video = torch.nan_to_num(video, nan=0.0, posinf=0.0, neginf=0.0)
        stacked = torch.stack([text, audio, video], dim=1)
        stacked = stacked + self.modal_tokens.unsqueeze(0)
        fused = self.encoder(stacked)
        fused = torch.nan_to_num(fused, nan=0.0, posinf=0.0, neginf=0.0)
        if self.pooling == "cls":
            pooled = fused[:, 0, :]
        elif self.pooling == "max":
            pooled = fused.max(dim=1).values
        elif self.pooling == "min":
            pooled = fused.min(dim=1).values
        else:
            pooled = fused.mean(dim=1)
        return self.output_norm(pooled)


class BidirectionalCrossAttentionCMT(nn.Module):
    """Bidirectional cross-attention fusion for text and audio sequences."""

    def __init__(self, hidden_dim: int, num_heads: int, dropout: float, pooling: str = "mean") -> None:
        super().__init__()
        self.pooling = pooling.lower()
        self.text_to_audio = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.audio_to_text = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.text_norm = nn.LayerNorm(hidden_dim)
        self.audio_norm = nn.LayerNorm(hidden_dim)
        self.output_norm = nn.LayerNorm(hidden_dim)
        self.dropout = nn.Dropout(dropout)

    @staticmethod
    def _ensure_mask(mask: torch.Tensor | None, shape: torch.Size, device: torch.device) -> torch.Tensor:
        if mask is None:
            return torch.ones(shape, dtype=torch.bool, device=device)
        return mask.bool()

    @staticmethod
    def _masked_pool(x: torch.Tensor, mask: torch.Tensor, pooling: str) -> torch.Tensor:
        pooling = pooling.lower()
        mask = mask.bool()
        valid = mask.unsqueeze(-1)
        if pooling == "cls":
            return x[:, 0, :]
        if pooling == "max":
            masked = x.masked_fill(~valid, float("-inf"))
            pooled = masked.max(dim=1).values
            pooled = torch.where(torch.isfinite(pooled), pooled, torch.zeros_like(pooled))
            return pooled
        if pooling == "min":
            masked = x.masked_fill(~valid, float("inf"))
            pooled = masked.min(dim=1).values
            pooled = torch.where(torch.isfinite(pooled), pooled, torch.zeros_like(pooled))
            return pooled
        summed = (x * valid).sum(dim=1)
        denom = valid.sum(dim=1).clamp(min=1)
        return summed / denom

    def forward(
        self,
        text: torch.Tensor,
        audio: torch.Tensor,
        text_mask: torch.Tensor | None = None,
        audio_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        text = torch.nan_to_num(text, nan=0.0, posinf=0.0, neginf=0.0)
        audio = torch.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        text_mask = self._ensure_mask(text_mask, text.shape[:2], text.device)
        audio_mask = self._ensure_mask(audio_mask, audio.shape[:2], audio.device)

        text_key_padding_mask = ~text_mask
        audio_key_padding_mask = ~audio_mask

        text_ctx, _ = self.text_to_audio(
            query=text,
            key=audio,
            value=audio,
            key_padding_mask=audio_key_padding_mask,
            need_weights=False,
        )
        audio_ctx, _ = self.audio_to_text(
            query=audio,
            key=text,
            value=text,
            key_padding_mask=text_key_padding_mask,
            need_weights=False,
        )

        text_ctx = self.text_norm(text + self.dropout(text_ctx))
        audio_ctx = self.audio_norm(audio + self.dropout(audio_ctx))
        fused_tokens = torch.cat([text_ctx, audio_ctx], dim=1)
        fused_mask = torch.cat([text_mask, audio_mask], dim=1)
        fused_tokens = torch.nan_to_num(fused_tokens, nan=0.0, posinf=0.0, neginf=0.0)
        pooled = self._masked_pool(fused_tokens, fused_mask, self.pooling)
        return self.output_norm(pooled)


class PretrainedBackboneEncoder(nn.Module):
    def __init__(self, model_name: str, target_dim: int, freeze_backbone: bool = True, is_audio: bool = False) -> None:
        super().__init__()
        if AutoModel is None:
            raise ImportError("transformers is required for pretrained encoder mode")
        self.is_audio = is_audio
        self.backbone = AutoModel.from_pretrained(model_name)
        hidden_size = int(getattr(self.backbone.config, "hidden_size", target_dim))
        self.proj = nn.Linear(hidden_size, target_dim)
        self.output_norm = nn.LayerNorm(target_dim)
        if freeze_backbone:
            for param in self.backbone.parameters():
                param.requires_grad = False

    def encode_sequence(
        self,
        inputs: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        inputs = torch.nan_to_num(inputs, nan=0.0, posinf=0.0, neginf=0.0)
        if self.is_audio:
            outputs = self.backbone(input_values=inputs, attention_mask=attention_mask)
        else:
            outputs = self.backbone(input_ids=inputs.long(), attention_mask=attention_mask)
        hidden = torch.nan_to_num(outputs.last_hidden_state, nan=0.0, posinf=0.0, neginf=0.0)
        if self.is_audio and attention_mask is not None:
            valid_lengths = attention_mask.long().sum(dim=1).to(hidden.device)
            if hasattr(self.backbone, "_get_feat_extract_output_lengths"):
                feat_lengths = self.backbone._get_feat_extract_output_lengths(valid_lengths).long()
                frame_ids = torch.arange(hidden.size(1), device=hidden.device).unsqueeze(0)
                mask = frame_ids < feat_lengths.unsqueeze(1)
            else:
                mask = torch.ones(hidden.shape[:2], dtype=torch.bool, device=hidden.device)
        elif attention_mask is not None and attention_mask.size(1) == hidden.size(1):
            mask = attention_mask.bool()
        else:
            mask = torch.ones(hidden.shape[:2], dtype=torch.bool, device=hidden.device)
        return hidden, mask

    def forward(self, inputs: torch.Tensor, attention_mask: torch.Tensor | None = None) -> torch.Tensor:
        hidden, mask = self.encode_sequence(inputs, attention_mask=attention_mask)
        valid = mask.unsqueeze(-1)
        summed = (hidden * valid).sum(dim=1)
        denom = valid.sum(dim=1).clamp(min=1)
        pooled = summed / denom
        pooled = self.proj(pooled)
        return self.output_norm(pooled)


class LegalMemoCMTPhase1(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.encoder_mode = config.encoder_mode.lower().strip()
        if self.encoder_mode in {"pretrained", "paper"}:
            self.text_encoder = PretrainedBackboneEncoder(
                model_name=config.text_model_name,
                target_dim=config.fusion_dim,
                freeze_backbone=config.freeze_text_backbone,
                is_audio=False,
            )
            self.audio_encoder = PretrainedBackboneEncoder(
                model_name=config.audio_model_name,
                target_dim=config.fusion_dim,
                freeze_backbone=config.freeze_audio_backbone,
                is_audio=True,
            )
        else:
            self.text_encoder = TextEncoder(
                vocab_size=config.vocab_size,
                embed_dim=config.text_dim,
                hidden_dim=config.fusion_dim,
                num_layers=config.num_layers,
                num_heads=config.num_heads,
                dropout=config.dropout,
            )
            self.audio_encoder = SequenceEncoder(
                input_dim=config.audio_dim,
                hidden_dim=config.fusion_dim,
                num_layers=config.num_layers,
                num_heads=config.num_heads,
                dropout=config.dropout,
            )
        self.video_encoder = SequenceEncoder(
            input_dim=config.video_dim,
            hidden_dim=config.fusion_dim,
            num_layers=config.num_layers,
            num_heads=config.num_heads,
            dropout=config.dropout,
        )
        self.legacy_fusion = CrossModalFusion(
            hidden_dim=config.fusion_dim,
            num_heads=config.num_heads,
            num_layers=config.num_layers,
            dropout=config.dropout,
            pooling=getattr(config, "fusion_pooling", "mean"),
        )
        self.paper_fusion = BidirectionalCrossAttentionCMT(
            hidden_dim=config.fusion_dim,
            num_heads=config.num_heads,
            dropout=config.dropout,
            pooling=getattr(config, "fusion_pooling", "mean"),
        )
        self.classifier = nn.Sequential(
            nn.LayerNorm(config.fusion_dim),
            nn.Linear(config.fusion_dim, config.fusion_dim),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.fusion_dim, config.num_classes),
        )

    def forward(
        self,
        text_tokens: torch.Tensor | None = None,
        audio_features: torch.Tensor | None = None,
        audio_mask: torch.Tensor | None = None,
        video_features: torch.Tensor | None = None,
        video_mask: torch.Tensor | None = None,
        text_input_ids: torch.Tensor | None = None,
        text_attention_mask: torch.Tensor | None = None,
        audio_waveform: torch.Tensor | None = None,
        audio_attention_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        text_present = (text_input_ids is not None and text_attention_mask is not None) or (
            text_tokens is not None and self.encoder_mode not in {"pretrained", "paper"}
        )
        audio_present = (audio_waveform is not None and audio_attention_mask is not None) or (
            audio_features is not None and self.encoder_mode not in {"pretrained", "paper"}
        )
        video_present = self.config.use_video and video_features is not None and video_mask is not None

        if video_present and not text_present and not audio_present:
            video_repr = self.video_encoder(video_features, mask=video_mask)
            logits = self.classifier(torch.nan_to_num(video_repr, nan=0.0, posinf=0.0, neginf=0.0))
            return torch.nan_to_num(logits, nan=0.0, posinf=0.0, neginf=0.0)

        if self.encoder_mode in {"pretrained", "paper"}:
            if text_input_ids is None:
                text_input_ids = text_tokens
            if audio_waveform is None:
                audio_waveform = audio_features
            if text_input_ids is None or text_attention_mask is None:
                raise ValueError("text_input_ids and text_attention_mask are required in pretrained encoder mode")
            if audio_waveform is None or audio_attention_mask is None:
                raise ValueError("audio_waveform and audio_attention_mask are required in pretrained encoder mode")
            text_seq, text_mask = self.text_encoder.encode_sequence(text_input_ids, attention_mask=text_attention_mask)
            audio_seq, audio_mask = self.audio_encoder.encode_sequence(audio_waveform, attention_mask=audio_attention_mask)
            if self.config.use_video and video_features is not None and video_mask is not None:
                text_repr = self.text_encoder(text_input_ids, attention_mask=text_attention_mask)
                audio_repr = self.audio_encoder(audio_waveform, attention_mask=audio_attention_mask)
            else:
                text_seq = self.text_encoder.output_norm(self.text_encoder.proj(text_seq))
                audio_seq = self.audio_encoder.output_norm(self.audio_encoder.proj(audio_seq))
                fused = self.paper_fusion(text_seq, audio_seq, text_mask=text_mask, audio_mask=audio_mask)
                logits = self.classifier(torch.nan_to_num(fused, nan=0.0, posinf=0.0, neginf=0.0))
                return torch.nan_to_num(logits, nan=0.0, posinf=0.0, neginf=0.0)
        else:
            if text_tokens is None or audio_features is None:
                raise ValueError("text_tokens and audio_features are required in legacy encoder mode")
            text_tokens = torch.nan_to_num(text_tokens, nan=0.0, posinf=0.0, neginf=0.0)
            audio_features = torch.nan_to_num(audio_features, nan=0.0, posinf=0.0, neginf=0.0)
            text_repr = self.text_encoder(text_tokens)
            audio_repr = self.audio_encoder(audio_features, mask=audio_mask)
        if video_features is None:
            raise ValueError("video_features must be provided")
        video_repr = self.video_encoder(video_features, mask=video_mask)
        fused = self.legacy_fusion(text_repr, audio_repr, video_repr)
        logits = self.classifier(torch.nan_to_num(fused, nan=0.0, posinf=0.0, neginf=0.0))
        return torch.nan_to_num(logits, nan=0.0, posinf=0.0, neginf=0.0)
