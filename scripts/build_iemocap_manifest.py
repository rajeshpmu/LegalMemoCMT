from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import PreprocessConfig, extract_video_features, load_audio_features, normalize_text


IEMOCAP_MAP_4WAY = {
    "ang": 0,
    "hap": 1,
    "neu": 2,
    "sad": 3,
}

LABEL_RE = re.compile(r"\[(?P<start>[0-9.]+) - (?P<end>[0-9.]+)\]\s+\[(?P<label>[a-z]{3})\]")


def find_transcription_file(session_root: Path, utt_id: str) -> Path | None:
    candidates = list((session_root / "dialog" / "transcriptions").glob("*.txt"))
    for path in candidates:
        if path.exists() and utt_id in path.read_text(encoding="utf-8", errors="ignore"):
            return path
    return None


def find_audio_file(session_root: Path, utt_id: str) -> Path | None:
    candidates = [
        session_root / "sentences" / "wav" / utt_id[: utt_id.rfind("_")] / f"{utt_id}.wav",
        session_root / "sentences" / "wav" / utt_id / f"{utt_id}.wav",
    ]
    for path in candidates:
        if path.exists():
            return path
    for path in session_root.rglob(f"{utt_id}.wav"):
        return path
    return None


def find_video_file(session_root: Path, utt_id: str) -> Path | None:
    candidates = [
        session_root / "sentences" / "video" / utt_id[: utt_id.rfind("_")] / f"{utt_id}.avi",
        session_root / "sentences" / "video" / utt_id / f"{utt_id}.avi",
    ]
    for path in candidates:
        if path.exists():
            return path
    for path in session_root.rglob(f"{utt_id}.avi"):
        return path
    return None


def parse_emotion_lines(path: Path) -> list[tuple[str, str]]:
    items = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("[") and "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 3:
                utt_id = parts[1].strip()
                label_part = parts[2].strip().split()[0]
                label = label_part[:3].lower()
                if label in IEMOCAP_MAP_4WAY:
                    items.append((utt_id, label))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an IEMOCAP manifest with extracted features")
    parser.add_argument("--iemocap-root", type=str, required=True, help="Path to the IEMOCAP release root")
    parser.add_argument("--output-root", type=str, default="data/processed/IEMOCAP", help="Output directory for features")
    parser.add_argument("--manifest-dir", type=str, default="data/manifests", help="Directory for output manifests")
    parser.add_argument("--frame-size", type=int, default=224)
    parser.add_argument("--num-frames", type=int, default=32)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--max-audio-seconds", type=float, default=10.0)
    args = parser.parse_args()

    root = Path(args.iemocap_root)
    output_root = Path(args.output_root)
    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    cfg = PreprocessConfig(frame_size=args.frame_size, num_frames=args.num_frames, sample_rate=args.sample_rate, max_audio_seconds=args.max_audio_seconds)

    rows = []
    for session_root in sorted(root.glob("Session*")):
        emo_dir = session_root / "dialog" / "EmoEvaluation"
        if not emo_dir.exists():
            continue
        for emo_file in sorted(emo_dir.glob("*.txt")):
            for utt_id, label in parse_emotion_lines(emo_file):
                audio_path = find_audio_file(session_root, utt_id)
                video_path = find_video_file(session_root, utt_id)
                if audio_path is None or video_path is None:
                    continue

                transcript_path = find_transcription_file(session_root, utt_id)
                transcript = ""
                if transcript_path is not None:
                    transcript = normalize_text(transcript_path.read_text(encoding="utf-8", errors="ignore"))

                sample_id = utt_id
                feat_dir = output_root / session_root.name
                video_feat_path = feat_dir / "video" / f"{sample_id}.npy"
                audio_feat_path = feat_dir / "audio" / f"{sample_id}.npy"
                video_feat_path.parent.mkdir(parents=True, exist_ok=True)
                audio_feat_path.parent.mkdir(parents=True, exist_ok=True)

                if not video_feat_path.exists():
                    video_features = extract_video_features(str(video_path), cfg)
                    np.save(video_feat_path, video_features)
                if not audio_feat_path.exists():
                    audio_features = load_audio_features(str(audio_path), cfg)
                    np.save(audio_feat_path, audio_features)

                rows.append(
                    {
                        "sample_id": sample_id,
                        "split": "train",
                        "label": IEMOCAP_MAP_4WAY[label],
                        "video_path": str(video_feat_path),
                        "audio_path": str(audio_feat_path),
                        "transcript": transcript,
                    }
                )

    out_csv = manifest_dir / "iemocap_4way.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Wrote {len(rows)} rows to {out_csv}")
    print("Note: IEMOCAP does not ship with official train/dev/test splits. Common practice is LOSO cross-validation.")


if __name__ == "__main__":
    main()
