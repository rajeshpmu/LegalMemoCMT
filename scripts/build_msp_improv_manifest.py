from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"sample_id", "split", "label", "transcript", "video_path", "audio_path"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an MSP-IMPROV manifest from exported metadata")
    parser.add_argument("--msp-root", type=str, default="data/MSP_IMPROV", help="Path to MSP-IMPROV workspace root")
    parser.add_argument("--manifest-dir", type=str, default="data/manifests", help="Directory for output manifests")
    parser.add_argument("--labels-csv", type=str, default="", help="CSV with labels and paths")
    args = parser.parse_args()

    msp_root = Path(args.msp_root)
    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    labels_csv = Path(args.labels_csv) if args.labels_csv else None
    if labels_csv is None:
        candidates = [msp_root / "labels.csv", msp_root / "metadata.csv", msp_root / "annotations.csv"]
        labels_csv = next((p for p in candidates if p.exists()), None)
    if labels_csv is None:
        raise FileNotFoundError(
            "No MSP-IMPROV labels CSV found. Run scripts/download_msp_improv.py with --write-template "
            "and then fill in the real rows."
        )

    df = pd.read_csv(labels_csv)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"MSP-IMPROV CSV is missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError(f"{labels_csv} contains no rows. Populate it with MSP-IMPROV metadata first.")

    rows = []
    for _, row in df.iterrows():
        sample_id = str(row["sample_id"]).strip()
        split = str(row["split"]).strip()
        label = int(row["label"])
        transcript = str(row["transcript"]).strip()
        video_path = Path(str(row["video_path"]))
        audio_path = Path(str(row["audio_path"]))
        if not video_path.is_absolute():
            video_path = msp_root / video_path
        if not audio_path.is_absolute():
            audio_path = msp_root / audio_path

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

    out_csv = manifest_dir / "msp_improv.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Wrote {len(rows)} rows to {out_csv}")
    print("MSP-IMPROV manifest built from exported metadata.")


if __name__ == "__main__":
    main()
