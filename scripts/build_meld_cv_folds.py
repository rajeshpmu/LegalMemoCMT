from __future__ import annotations

import argparse
import json
import re
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd


SAMPLE_ID_RE = re.compile(r"^(?P<split>train|dev|test)_dia(?P<dialogue>\d+)_utt(?P<utterance>\d+)$")


def parse_dialogue_key(sample_id: str, fallback_split: str) -> str:
    match = SAMPLE_ID_RE.match(sample_id)
    if match:
        return f"{match.group('split')}_dia{int(match.group('dialogue'))}"
    return f"{fallback_split}_dia{sample_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MELD 5-fold CV manifests from the raw manifest")
    parser.add_argument("--manifest", type=str, default="data/manifests/meld_raw.csv", help="Input raw MELD manifest")
    parser.add_argument("--output-dir", type=str, default="data/manifests/meld_cv", help="Directory for fold manifests")
    parser.add_argument("--num-folds", type=int, default=5, help="Number of CV folds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for fold assignment")
    parser.add_argument(
        "--base-splits",
        type=str,
        default="train,dev",
        help="Comma-separated manifest splits to include in CV folds; test is typically held out separately",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(manifest_path)
    required = {"sample_id", "split", "label", "video_path", "audio_path", "transcript"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Manifest is missing required columns: {sorted(missing)}")

    base_splits = {part.strip().lower() for part in args.base_splits.split(",") if part.strip()}
    if not base_splits:
        raise ValueError("At least one base split must be provided")

    cv_df = df[df["split"].str.lower().isin(base_splits)].copy()
    if cv_df.empty:
        raise ValueError(f"No rows found for base splits {sorted(base_splits)} in {manifest_path}")

    cv_df["dialogue_key"] = [
        parse_dialogue_key(str(sample_id), str(split).lower())
        for sample_id, split in zip(cv_df["sample_id"], cv_df["split"], strict=False)
    ]

    unique_dialogues = sorted(cv_df["dialogue_key"].unique().tolist())
    rng = random.Random(args.seed)
    rng.shuffle(unique_dialogues)

    fold_to_dialogues: dict[int, list[str]] = defaultdict(list)
    for idx, dialogue_key in enumerate(unique_dialogues):
        fold_to_dialogues[idx % args.num_folds].append(dialogue_key)

    summary = {
        "manifest": str(manifest_path),
        "output_dir": str(output_dir),
        "num_folds": int(args.num_folds),
        "seed": int(args.seed),
        "base_splits": sorted(base_splits),
        "folds": [],
    }

    assignment_rows = []
    for fold_idx in range(args.num_folds):
        val_dialogues = set(fold_to_dialogues[fold_idx])
        train_df = cv_df[~cv_df["dialogue_key"].isin(val_dialogues)].copy()
        val_df = cv_df[cv_df["dialogue_key"].isin(val_dialogues)].copy()

        train_path = output_dir / f"meld_fold_{fold_idx}_train.csv"
        val_path = output_dir / f"meld_fold_{fold_idx}_val.csv"
        train_df.drop(columns=["dialogue_key"]).to_csv(train_path, index=False)
        val_df.drop(columns=["dialogue_key"]).to_csv(val_path, index=False)

        summary["folds"].append(
            {
                "fold": fold_idx,
                "train_rows": int(len(train_df)),
                "val_rows": int(len(val_df)),
                "train_path": str(train_path),
                "val_path": str(val_path),
            }
        )

        for dialogue_key in val_dialogues:
            assignment_rows.append({"dialogue_key": dialogue_key, "fold": fold_idx})

    assignments_path = output_dir / "meld_fold_assignments.csv"
    pd.DataFrame(sorted(assignment_rows, key=lambda row: (row["fold"], row["dialogue_key"]))).to_csv(assignments_path, index=False)
    summary["assignments_path"] = str(assignments_path)

    summary_path = output_dir / "meld_cv_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    for fold in summary["folds"]:
        print(
            f"Fold {fold['fold']}: train_rows={fold['train_rows']} val_rows={fold['val_rows']} "
            f"train={fold['train_path']} val={fold['val_path']}"
        )
    print(f"Wrote assignments to {assignments_path}")
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
