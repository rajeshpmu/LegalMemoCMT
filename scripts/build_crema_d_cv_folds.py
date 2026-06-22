from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd


def speaker_key(sample_id: str) -> str:
    # CREMA-D filenames begin with the speaker id, e.g. 1001_IEO_NEU_XX.
    return str(sample_id).split("_", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build speaker-independent CREMA-D CV manifests")
    parser.add_argument("--manifest", type=str, default="data/manifests/crema_d.csv", help="Input CREMA-D manifest")
    parser.add_argument("--output-dir", type=str, default="data/manifests/crema_d_cv", help="Directory for fold manifests")
    parser.add_argument("--num-folds", type=int, default=5, help="Number of CV folds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for fold assignment")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(manifest_path)
    required = {"sample_id", "split", "label", "video_path", "audio_path", "transcript"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Manifest is missing required columns: {sorted(missing)}")

    # Use the full manifest for cross-validation. The goal is to create
    # speaker-independent folds rather than a single held-out train/val/test split.
    cv_df = df.copy()
    cv_df["speaker_id"] = cv_df["sample_id"].astype(str).map(speaker_key)

    unique_speakers = sorted(cv_df["speaker_id"].unique().tolist())
    rng = random.Random(args.seed)
    rng.shuffle(unique_speakers)

    fold_to_speakers: dict[int, list[str]] = defaultdict(list)
    for idx, speaker in enumerate(unique_speakers):
        fold_to_speakers[idx % args.num_folds].append(speaker)

    summary = {
        "manifest": str(manifest_path),
        "output_dir": str(output_dir),
        "num_folds": int(args.num_folds),
        "seed": int(args.seed),
        "folds": [],
    }

    assignment_rows = []
    for fold_idx in range(args.num_folds):
        val_speakers = set(fold_to_speakers[fold_idx])
        train_df = cv_df[~cv_df["speaker_id"].isin(val_speakers)].copy()
        val_df = cv_df[cv_df["speaker_id"].isin(val_speakers)].copy()

        train_path = output_dir / f"crema_d_fold_{fold_idx}_train.csv"
        val_path = output_dir / f"crema_d_fold_{fold_idx}_val.csv"
        train_df.drop(columns=["speaker_id"]).to_csv(train_path, index=False)
        val_df.drop(columns=["speaker_id"]).to_csv(val_path, index=False)

        summary["folds"].append(
            {
                "fold": fold_idx,
                "train_rows": int(len(train_df)),
                "val_rows": int(len(val_df)),
                "train_path": str(train_path),
                "val_path": str(val_path),
                "train_speakers": len(unique_speakers) - len(val_speakers),
                "val_speakers": len(val_speakers),
            }
        )

        for speaker in val_speakers:
            assignment_rows.append({"speaker_id": speaker, "fold": fold_idx})

    assignments_path = output_dir / "crema_d_fold_assignments.csv"
    pd.DataFrame(sorted(assignment_rows, key=lambda row: (row["fold"], row["speaker_id"]))).to_csv(assignments_path, index=False)
    summary["assignments_path"] = str(assignments_path)

    summary_path = output_dir / "crema_d_cv_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    for fold in summary["folds"]:
        print(
            f"Fold {fold['fold']}: train_rows={fold['train_rows']} val_rows={fold['val_rows']} "
            f"train_speakers={fold['train_speakers']} val_speakers={fold['val_speakers']}"
        )
    print(f"Wrote assignments to {assignments_path}")
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
