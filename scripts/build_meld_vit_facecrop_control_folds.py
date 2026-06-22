from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _load_sample_table(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"sample_id", "split", "label", "video_path", "audio_path", "transcript"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Manifest is missing required columns: {sorted(missing)}")
    return df


def _subset_by_sample_ids(source: pd.DataFrame, sample_ids: list[str]) -> tuple[pd.DataFrame, list[str]]:
    indexed = source.set_index("sample_id", drop=False)
    rows = []
    missing: list[str] = []
    for sample_id in sample_ids:
        if sample_id in indexed.index:
            rows.append(indexed.loc[sample_id])
        else:
            missing.append(sample_id)
    if rows:
        subset = pd.DataFrame(rows).reset_index(drop=True)
    else:
        subset = source.iloc[0:0].copy()
    return subset, missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build face-crop MELD control folds using the paper-aligned MELD split as reference"
    )
    parser.add_argument(
        "--facecrop-manifest",
        type=str,
        default="data/manifests/meld_vit_facecrop.csv",
        help="Face-crop manifest containing the ViT facial embedding paths",
    )
    parser.add_argument(
        "--paper-fold-dir",
        type=str,
        default="data/manifests/meld_cv",
        help="Existing paper-aligned MELD fold directory used as the control split reference",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/manifests/meld_vit_facecrop_control_cv",
        help="Directory for the face-crop control fold CSVs",
    )
    parser.add_argument("--num-folds", type=int, default=5, help="Number of folds to build")
    args = parser.parse_args()

    facecrop_manifest = Path(args.facecrop_manifest)
    paper_fold_dir = Path(args.paper_fold_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    face_df = _load_sample_table(facecrop_manifest)
    face_ids = set(face_df["sample_id"].astype(str))

    summary = {
        "facecrop_manifest": str(facecrop_manifest),
        "paper_fold_dir": str(paper_fold_dir),
        "output_dir": str(output_dir),
        "num_folds": int(args.num_folds),
        "folds": [],
    }
    assignment_rows: list[dict[str, object]] = []

    for fold_idx in range(args.num_folds):
        paper_train = paper_fold_dir / f"meld_fold_{fold_idx}_train.csv"
        paper_val = paper_fold_dir / f"meld_fold_{fold_idx}_val.csv"
        if not paper_train.exists() or not paper_val.exists():
            raise FileNotFoundError(
                f"Missing paper-aligned fold CSVs for fold {fold_idx}: {paper_train} / {paper_val}"
            )

        train_ids = pd.read_csv(paper_train)["sample_id"].astype(str).tolist()
        val_ids = pd.read_csv(paper_val)["sample_id"].astype(str).tolist()

        train_df, train_missing = _subset_by_sample_ids(face_df, train_ids)
        val_df, val_missing = _subset_by_sample_ids(face_df, val_ids)

        train_df.to_csv(output_dir / f"meld_fold_{fold_idx}_train.csv", index=False)
        val_df.to_csv(output_dir / f"meld_fold_{fold_idx}_val.csv", index=False)

        for sample_id in val_df["sample_id"].astype(str).tolist():
            assignment_rows.append({"sample_id": sample_id, "fold": fold_idx, "split": "val"})

        summary["folds"].append(
            {
                "fold": fold_idx,
                "paper_train_rows": int(len(train_ids)),
                "paper_val_rows": int(len(val_ids)),
                "facecrop_train_rows": int(len(train_df)),
                "facecrop_val_rows": int(len(val_df)),
                "train_missing": train_missing,
                "val_missing": val_missing,
            }
        )

        print(
            f"Fold {fold_idx}: paper_train_rows={len(train_ids)} paper_val_rows={len(val_ids)} "
            f"facecrop_train_rows={len(train_df)} facecrop_val_rows={len(val_df)}"
        )
        if train_missing:
            print(f"  Missing train sample_ids in face-crop manifest: {train_missing}")
        if val_missing:
            print(f"  Missing val sample_ids in face-crop manifest: {val_missing}")

    assignments_path = output_dir / "meld_fold_assignments.csv"
    pd.DataFrame(assignment_rows).to_csv(assignments_path, index=False)
    summary["assignments_path"] = str(assignments_path)

    summary_path = output_dir / "meld_cv_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote assignments to {assignments_path}")
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
