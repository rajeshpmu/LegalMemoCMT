from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the local Hugging Face/pyannote diarization setup")
    parser.add_argument("--model", default="pyannote/speaker-diarization-3.1")
    parser.add_argument("--load-model", action="store_true", help="Also download/load the model to verify access")
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    print(f"python={sys.executable}")
    if not token:
        raise SystemExit("FAIL: HF_TOKEN is not set")
    print("HF_TOKEN=present")
    try:
        import torch
        print(f"torch={torch.__version__}")
    except Exception as exc:
        raise SystemExit(f"FAIL: torch import failed: {exc}") from exc
    try:
        import torchaudio
        print(f"torchaudio={torchaudio.__version__} AudioMetaData={hasattr(torchaudio, 'AudioMetaData')}")
        if not hasattr(torchaudio, "AudioMetaData"):
            raise RuntimeError("torchaudio.AudioMetaData is missing; use the isolated torch/torchaudio 2.2 environment")
    except Exception as exc:
        raise SystemExit(f"FAIL: torchaudio compatibility check failed: {exc}") from exc
    try:
        import pyannote.audio
        print(f"pyannote.audio={pyannote.audio.__version__}")
    except Exception as exc:
        raise SystemExit(f"FAIL: pyannote.audio import failed: {exc}") from exc
    if args.load_model:
        try:
            from huggingface_hub import HfApi

            HfApi().model_info(args.model, token=token)
            print(f"model_repo_access=PASS model={args.model}")
        except Exception as exc:
            error_name = type(exc).__name__
            print(f"model_repo_access=FAIL error_type={error_name} detail={exc}")
            print(
                "Check that HF_TOKEN is a real read token, that the token is available in this shell, "
                "and that the pyannote model conditions have been accepted in the browser."
            )
            raise SystemExit("FAIL: Hugging Face model repository access failed") from exc
        from pyannote.audio import Pipeline

        try:
            pipeline = Pipeline.from_pretrained(args.model, token=token)
        except TypeError as exc:
            if "unexpected keyword argument 'token'" not in str(exc):
                raise
            try:
                pipeline = Pipeline.from_pretrained(args.model, use_auth_token=token)
            except Exception as fallback_exc:
                raise SystemExit(
                    "FAIL: pyannote pipeline dependencies could not be loaded. "
                    "Check access to gated dependencies such as pyannote/segmentation-3.0. "
                    f"detail={fallback_exc}"
                ) from fallback_exc
        except Exception as exc:
            raise SystemExit(f"FAIL: pyannote pipeline loading failed: {exc}") from exc
        if pipeline is None:
            raise SystemExit(
                "FAIL: Hugging Face returned no diarization pipeline after repository access passed; "
                "check model revision and pyannote compatibility"
            )
        print(f"model_access=PASS model={args.model}")
    else:
        print("model_access=NOT_CHECKED use --load-model for Hugging Face access verification")
    print("status=PASS")


if __name__ == "__main__":
    main()
