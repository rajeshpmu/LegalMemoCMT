from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {"sample_id", "split", "label", "transcript", "video_path", "audio_path"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a CREMA-D manifest from exported metadata")
    parser.add_argument("--crema-root", type=str, default="data/CREMA_D", help="Path to CREMA-D workspace root")
    parser.add_argument("--manifest-dir", type=str, default="data/manifests", help="Directory for output manifests")
    parser.add_argument("--labels-csv", type=str, default="", help="CSV with labels and paths")
    args = parser.parse_args()

    crema_root = Path(args.crema_root)
    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    labels_csv = Path(args.labels_csv) if args.labels_csv else None
    if labels_csv is None:
        candidates = [crema_root / "labels.csv", crema_root / "metadata.csv", crema_root / "annotations.csv"]
        labels_csv = next((p for p in candidates if p.exists()), None)
    if labels_csv is None:
        raise FileNotFoundError(
            "No CREMA-D labels CSV found. Run scripts/download_crema_d.py with --write-template "
            "and then fill in the real rows."
        )

    df = pd.read_csv(labels_csv)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CREMA-D CSV is missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError(f"{labels_csv} contains no rows. Populate it with CREMA-D metadata first.")

    def looks_like_media_root(root: Path) -> bool:
        return (root / "AudioWAV").exists() and (root / "VideoFlash").exists()

    root_candidates = [crema_root]
    if crema_root.name != "CREMA_D_repo":
        root_candidates.append(crema_root.parent / "CREMA_D_repo")
    if crema_root.name != "CREMA_D":
        root_candidates.append(crema_root.parent / "CREMA_D")
    if labels_csv is not None:
        root_candidates.append(Path(labels_csv).resolve().parent)

    media_root = next((root for root in root_candidates if looks_like_media_root(root)), crema_root)
    if media_root != crema_root:
        print(f"Using media root {media_root} instead of {crema_root}")

    rows = []
    for _, row in df.iterrows():
        sample_id = str(row["sample_id"]).strip()
        split = str(row["split"]).strip()
        label = int(row["label"])
        transcript = str(row["transcript"]).strip()
        video_path = Path(str(row["video_path"]))
        audio_path = Path(str(row["audio_path"]))
        if not video_path.is_absolute():
            video_path = media_root / video_path
        if not audio_path.is_absolute():
            audio_path = media_root / audio_path

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

    out_csv = manifest_dir / "crema_d.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"Wrote {len(rows)} rows to {out_csv}")
    print("CREMA-D manifest built from exported metadata.")


if __name__ == "__main__":
    main()
