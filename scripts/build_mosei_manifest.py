from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"video_id", "segment_id", "split", "label", "transcript", "video_path", "audio_path"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a CMU-MOSEI manifest from exported feature metadata")
    parser.add_argument("--mosei-root", type=str, default="data/MOSEI", help="Path to MOSEI workspace root")
    parser.add_argument("--manifest-dir", type=str, default="data/manifests", help="Directory for output manifests")
    parser.add_argument("--labels-csv", type=str, default="", help="Optional CSV with labels and transcripts")
    args = parser.parse_args()

    mosei_root = Path(args.mosei_root)
    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    labels_csv = Path(args.labels_csv) if args.labels_csv else None
    if labels_csv is None:
        candidates = [mosei_root / "labels.csv", mosei_root / "metadata.csv", mosei_root / "annotations.csv"]
        labels_csv = next((p for p in candidates if p.exists()), None)
    if labels_csv is None:
        raise FileNotFoundError(
            "No MOSEI labels CSV found. Run scripts/download_mosei.py with --write-template, "
            "then fill in the exported labels/metadata columns."
        )

    df = pd.read_csv(labels_csv)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"MOSEI labels CSV is missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError(
            f"{labels_csv} contains no data rows. Fill the template with MOSEI metadata "
            "before building the manifest."
        )

    rows = []
    for _, row in df.iterrows():
        split = str(row["split"])
        label = int(row["label"])
        transcript = str(row["transcript"]).strip()
        video_path = Path(str(row["video_path"]))
        audio_path = Path(str(row["audio_path"]))
        if not video_path.is_absolute():
            video_path = mosei_root / video_path
        if not audio_path.is_absolute():
            audio_path = mosei_root / audio_path

        video_id = str(row["video_id"])
        segment_id = str(row["segment_id"])
        sample_id = f"{video_id}_{segment_id}"

        rows.append(
            {
                "sample_id": sample_id,
                "split": split,
                "label": label,
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "transcript": transcript,
            }
        )

    out_csv = manifest_dir / "mosei.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Wrote {len(rows)} rows to {out_csv}")
    print("CMU-MOSEI manifest built from exported metadata.")


if __name__ == "__main__":
    main()
