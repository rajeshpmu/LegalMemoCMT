from dataclasses import dataclass


@dataclass
class ModelConfig:
    encoder_mode: str = "legacy"
    fusion_mode: str = "legacy"
    vocab_size: int = 30000
    text_dim: int = 256
    audio_dim: int = 128
    video_dim: int = 128
    fusion_dim: int = 256
    num_heads: int = 4
    num_layers: int = 2
    dropout: float = 0.1
    num_classes: int = 7
    max_text_len: int = 128
    max_audio_len: int = 256
    max_video_len: int = 32
    fusion_pooling: str = "mean"
    text_model_name: str = "bert-base-uncased"
    audio_model_name: str = "facebook/hubert-base-ls960"
    freeze_text_backbone: bool = True
    freeze_audio_backbone: bool = True
    use_video: bool = True


@dataclass
class TrainConfig:
    seed: int = 42
    batch_size: int = 8
    epochs: int = 10
    lr: float = 3e-4
    weight_decay: float = 1e-2
    grad_clip: float = 1.0
    device: str = "auto"
    log_every: int = 20
    output_dir: str = "results/phase1"
