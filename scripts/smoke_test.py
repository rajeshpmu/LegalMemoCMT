from __future__ import annotations

import sys
from pathlib import Path

try:
    import torch
except Exception as exc:  # pragma: no cover
    print("torch is not installed in this environment.")
    print("Install dependencies first, then run this script again.")
    raise SystemExit(1) from exc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models import LegalMemoCMTPhase1, ModelConfig


def main() -> None:
    config = ModelConfig()
    model = LegalMemoCMTPhase1(config)
    model.eval()

    batch_size = 2
    text_tokens = torch.randint(1, config.vocab_size, (batch_size, config.max_text_len))
    audio_features = torch.randn(batch_size, config.max_audio_len, config.audio_dim)
    audio_mask = torch.ones(batch_size, config.max_audio_len, dtype=torch.bool)
    video_features = torch.randn(batch_size, config.max_video_len, config.video_dim)
    video_mask = torch.ones(batch_size, config.max_video_len, dtype=torch.bool)

    with torch.no_grad():
        logits = model(
            text_tokens=text_tokens,
            audio_features=audio_features,
            audio_mask=audio_mask,
            video_features=video_features,
            video_mask=video_mask,
        )

    print("Smoke test passed.")
    print(f"Input batch size: {batch_size}")
    print(f"Logits shape: {tuple(logits.shape)}")
    print(f"Expected classes: {config.num_classes}")


if __name__ == "__main__":
    main()
