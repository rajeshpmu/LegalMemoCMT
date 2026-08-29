"""Add independent audio SER evidence to a Clancy manifest.

The outputs are suggestions/evidence only. Existing canonical or human labels
are never overwritten. Odyssey produces continuous valence/arousal/dominance;
SpeechBrain provides a categorical cross-check.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np


def clean(value: object) -> str:
    return str(value or "").strip()


def audio_path(row: dict[str, str]) -> str:
    for key in ("clip_audio_path", "audio_clip_path", "audio_path"):
        value = clean(row.get(key))
        if value and Path(value).exists():
            return value
    return ""


def load_audio(path: str, sample_rate: int) -> np.ndarray:
    import librosa

    waveform, _ = librosa.load(path, sr=sample_rate, mono=True)
    return np.asarray(waveform, dtype=np.float32)


def load_odyssey(model_name: str):
    import torch
    from transformers import AutoModelForAudioClassification

    model = AutoModelForAudioClassification.from_pretrained(model_name, trust_remote_code=True)
    model.eval()
    return model, torch


def odyssey_predict(model, torch, waveform: np.ndarray) -> dict[str, float]:
    sample_rate = int(getattr(model.config, "sampling_rate", 16000))
    max_length = int(getattr(model.config, "maxlen", sample_rate * 12))
    if len(waveform) > max_length:
        waveform = waveform[:max_length]
    mean = float(getattr(model.config, "mean", 0.0))
    std = float(getattr(model.config, "std", 1.0))
    normalized = (waveform - mean) / (std + 1e-6)
    tensor = torch.tensor(normalized, dtype=torch.float32).unsqueeze(0)
    mask = torch.ones((1, len(normalized)), dtype=torch.long)
    with torch.no_grad():
        output = model(tensor, mask)
    values = output.logits[0].detach().cpu().numpy().astype(float).tolist() if hasattr(output, "logits") else output[0].detach().cpu().numpy().astype(float).tolist()
    labels = {int(k): str(v).lower() for k, v in getattr(model.config, "id2label", {}).items()}
    result = {}
    for index, value in enumerate(values):
        label = labels.get(index, str(index)).replace(" ", "_")
        result[label] = round(float(value), 6)
    return result


def load_speechbrain(model_name: str, cache_dir: Path):
    try:
        from speechbrain.inference.classifiers import EncoderClassifier
    except ImportError:
        from speechbrain.pretrained import EncoderClassifier
    classifier = EncoderClassifier.from_hparams(source=model_name, savedir=str(cache_dir))
    return classifier


def speechbrain_predict(classifier, path: str) -> tuple[str, float]:
    # The repository's custom interface declares wav2vec2 -> avg_pool ->
    # output_mlp.  Some SpeechBrain releases route classify_file through a
    # generic `compute_features` hook that this checkpoint does not provide.
    # Calling the declared modules directly avoids that incompatible hook.
    import torch

    waveform = classifier.load_audio(path)
    batch = waveform.unsqueeze(0).to(classifier.device).float()
    lengths = torch.ones(batch.shape[0], device=classifier.device)
    with torch.no_grad():
        encoded = classifier.mods.wav2vec2(batch)
        pooled = classifier.mods.avg_pool(encoded, lengths)
        pooled = pooled.view(pooled.shape[0], -1)
        logits = classifier.mods.output_mlp(pooled)
        probabilities = classifier.hparams.softmax(logits)
        confidence, index = torch.max(probabilities, dim=-1)
        labels = classifier.hparams.label_encoder.decode_torch(index)
    label = labels[0] if isinstance(labels, (list, tuple)) else str(labels)
    return str(label).strip().lower(), round(float(confidence[0]), 6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--odyssey-model", default="3loi/SER-Odyssey-Baseline-WavLM-Multi-Attributes")
    parser.add_argument("--speechbrain-model", default="speechbrain/emotion-recognition-wav2vec2-IEMOCAP")
    parser.add_argument("--cache-dir", default="data/processed/phase2/clancy/audio_ser_model_cache")
    parser.add_argument("--skip-odyssey", action="store_true")
    parser.add_argument("--skip-speechbrain", action="store_true")
    args = parser.parse_args()

    if args.skip_odyssey and args.skip_speechbrain:
        raise SystemExit("At least one audio model must be enabled")
    input_path = Path(args.input_csv)
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if args.max_rows > 0:
        rows = rows[: args.max_rows]
    if not rows:
        raise SystemExit("No rows selected")

    cache_dir = Path(args.cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    odyssey = None; torch = None; speechbrain = None
    model_errors: list[str] = []
    if not args.skip_odyssey:
        try:
            odyssey, torch = load_odyssey(args.odyssey_model)
            if args.device != "cpu":
                odyssey.to(args.device)
        except Exception as exc:
            model_errors.append(f"odyssey_load: {exc}")
    if not args.skip_speechbrain:
        try:
            speechbrain = load_speechbrain(args.speechbrain_model, cache_dir / "speechbrain")
        except Exception as exc:
            model_errors.append(f"speechbrain_load: {exc}")

    output_rows: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()
    for row in rows:
        enriched = dict(row)
        path = audio_path(row)
        enriched["audio_ser_audio_path"] = path
        enriched["audio_ser_status"] = "OK" if path else "MISSING_AUDIO"
        enriched["audio_ser_error"] = ""
        if not path:
            status_counts["MISSING_AUDIO"] += 1
            output_rows.append(enriched); continue
        errors = []
        if odyssey is not None:
            try:
                sampling_rate = int(getattr(odyssey.config, "sampling_rate", 16000))
                prediction = odyssey_predict(odyssey, torch, load_audio(path, sampling_rate))
                for label in ("valence", "arousal", "dominance"):
                    if label in prediction:
                        enriched[f"audio_{label}"] = str(prediction[label])
                        if label == "arousal":
                            enriched["audio_excitement"] = str(prediction[label])
                enriched["audio_affect_model"] = args.odyssey_model
                enriched["audio_ser_odyssey_status"] = "OK"
            except Exception as exc:
                enriched["audio_ser_odyssey_status"] = "FAILED"
                errors.append(f"odyssey: {exc}")
        else:
            enriched["audio_ser_odyssey_status"] = "NOT_LOADED"
        if speechbrain is not None:
            try:
                label, confidence = speechbrain_predict(speechbrain, path)
                enriched["audio_emotion_candidate"] = label
                enriched["audio_emotion_confidence"] = str(confidence)
                enriched["audio_emotion_model"] = args.speechbrain_model
                enriched["audio_ser_speechbrain_status"] = "OK"
            except Exception as exc:
                enriched["audio_ser_speechbrain_status"] = "FAILED"
                errors.append(f"speechbrain: {exc}")
        else:
            enriched["audio_ser_speechbrain_status"] = "NOT_LOADED"
        enriched["audio_ser_error"] = " | ".join(errors)
        enriched["audio_ser_status"] = "OK" if not errors else "PARTIAL" if len(errors) < 2 else "FAILED"
        status_counts[enriched["audio_ser_status"]] += 1
        output_rows.append(enriched)

    output_path = Path(args.output_csv); output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(output_rows[0])
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(output_rows)
    summary = {
        "input_csv": str(input_path), "output_csv": str(output_path), "rows_processed": len(output_rows),
        "odyssey_model": None if args.skip_odyssey else args.odyssey_model,
        "speechbrain_model": None if args.skip_speechbrain else args.speechbrain_model,
        "status_counts": dict(status_counts), "model_load_errors": model_errors,
        "odyssey_success_rows": sum(row.get("audio_ser_odyssey_status") == "OK" for row in output_rows),
        "speechbrain_success_rows": sum(row.get("audio_ser_speechbrain_status") == "OK" for row in output_rows),
        "audio_paths_missing": sum(not row.get("audio_ser_audio_path") for row in output_rows),
        "canonical_labels_overwritten": False,
        "notes": [
            "Odyssey values are continuous audio valence/excitement/dominance evidence, approximately in the model's 0-1 range; they are not basic-emotion labels.",
            "audio_excitement is the project-facing alias of the model's audio_arousal output; audio_arousal is retained for loader and provenance compatibility.",
            "SpeechBrain categorical output is a cross-check trained on IEMOCAP and is not the LegalMemoCMT gold label.",
            "Existing emotion, basic-emotion, and courtroom-affect fields are preserved.",
            "Long audio clips are truncated to the Odyssey model's configured maximum input length when required.",
        ],
    }
    summary_path = Path(args.summary_json); summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if model_errors and status_counts.get("FAILED", 0) == len(output_rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
