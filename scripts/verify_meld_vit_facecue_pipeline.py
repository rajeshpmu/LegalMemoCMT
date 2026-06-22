from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_meld_manifest import EMOTION_MAP, find_meld_clip


SAMPLE_ID_RE = re.compile(r"^(?P<split>train|dev|test)_dia(?P<dialogue>\d+)_utt(?P<utterance>\d+)$")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the MELD ViT facial-cue preparation pipeline")
    parser.add_argument("--meld-root", type=str, default="data/MELD", help="Path to the MELD dataset root")
    parser.add_argument(
        "--manifest",
        type=str,
        default="data/manifests/meld_vit_facecue.csv",
        help="Path to the generated facial-cue manifest",
    )
    parser.add_argument(
        "--fold-dir",
        type=str,
        default="data/manifests/meld_vit_facecue_cv",
        help="Directory containing the CV folds generated from the facial-cue manifest",
    )
    parser.add_argument(
        "--require-splits",
        type=str,
        default="train,dev,test",
        help="Comma-separated MELD splits that must be present in the manifest",
    )
    return parser.parse_args()


def build_expected_ids(meld_root: Path, required_splits: set[str]) -> set[str]:
    expected: set[str] = set()
    ann_dir = meld_root / "annotations"
    raw_root = meld_root / "raw"

    for split in sorted(required_splits):
        csv_path = ann_dir / f"{split}_sent_emo.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            emotion = str(row["Emotion"]).strip().lower()
            if emotion not in EMOTION_MAP:
                continue
            dialogue_id = int(row["Dialogue_ID"])
            utterance_id = int(row["Utterance_ID"])
            try:
                find_meld_clip(raw_root, split, dialogue_id, utterance_id)
            except Exception:
                continue
            expected.add(f"{split}_dia{dialogue_id}_utt{utterance_id}")
    return expected


def infer_dialogue_key(sample_id: str) -> str:
    match = SAMPLE_ID_RE.match(sample_id)
    if not match:
        return sample_id
    return f"{match.group('split')}_dia{int(match.group('dialogue'))}"


def main() -> int:
    args = parse_args()
    meld_root = Path(args.meld_root)
    manifest_path = Path(args.manifest)
    fold_dir = Path(args.fold_dir)
    required_splits = {part.strip().lower() for part in args.require_splits.split(",") if part.strip()}

    results: list[CheckResult] = []

    if not manifest_path.exists():
        results.append(CheckResult("manifest_exists", False, f"Missing manifest: {manifest_path}"))
        _print_summary(results)
        return 1

    df = pd.read_csv(manifest_path)
    required_cols = {"sample_id", "split", "label", "video_path", "audio_path", "transcript"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        results.append(CheckResult("manifest_columns", False, f"Missing columns: {sorted(missing_cols)}"))
        _print_summary(results)
        return 1

    results.append(CheckResult("manifest_exists", True, f"Found manifest with {len(df)} rows"))

    if df.empty:
        results.append(CheckResult("manifest_non_empty", False, "Manifest has zero rows"))
        _print_summary(results)
        return 1
    results.append(CheckResult("manifest_non_empty", True, f"Manifest rows: {len(df)}"))

    manifest_splits = {str(s).strip().lower() for s in df["split"].dropna().unique().tolist()}
    missing_required_splits = sorted(required_splits - manifest_splits)
    if missing_required_splits:
        results.append(
            CheckResult(
                "split_coverage",
                False,
                f"Missing required splits in manifest: {missing_required_splits}; present={sorted(manifest_splits)}",
            )
        )
    else:
        results.append(CheckResult("split_coverage", True, f"Present splits: {sorted(manifest_splits)}"))

    expected_ids = build_expected_ids(meld_root, required_splits)
    manifest_ids = set(df["sample_id"].astype(str).tolist())
    missing_ids = sorted(expected_ids - manifest_ids)
    extra_ids = sorted(manifest_ids - expected_ids)
    if missing_ids or extra_ids:
        detail = (
            f"expected={len(expected_ids)}, manifest={len(manifest_ids)}, "
            f"missing={len(missing_ids)}, extra={len(extra_ids)}"
        )
        if missing_ids:
            detail += f"; first_missing={missing_ids[:5]}"
        if extra_ids:
            detail += f"; first_extra={extra_ids[:5]}"
        results.append(CheckResult("manifest_completeness", False, detail))
    else:
        results.append(CheckResult("manifest_completeness", True, f"Exact match against expected IDs: {len(expected_ids)}"))

    missing_files = []
    shapes = set()
    hidden_dim = None
    zero_len = 0
    nonfinite = 0
    for idx, row in df.iterrows():
        sample_id = str(row["sample_id"])
        video_path = Path(str(row["video_path"]))
        audio_path = Path(str(row["audio_path"]))

        if not video_path.exists():
            missing_files.append(f"{sample_id}: missing video_path={video_path}")
            continue
        if not audio_path.exists():
            missing_files.append(f"{sample_id}: missing audio_path={audio_path}")
            continue

        try:
            arr = np.load(video_path)
        except Exception as exc:
            missing_files.append(f"{sample_id}: failed to load embedding {video_path} ({exc})")
            continue

        if arr.ndim != 2:
            missing_files.append(f"{sample_id}: embedding rank {arr.ndim} != 2")
            continue
        if arr.shape[0] == 0:
            zero_len += 1
        if not np.isfinite(arr).all():
            nonfinite += 1
        hidden_dim = arr.shape[1] if hidden_dim is None else hidden_dim
        shapes.add(tuple(arr.shape))

    if missing_files:
        results.append(CheckResult("file_existence_and_load", False, f"{len(missing_files)} issues; first={missing_files[:5]}"))
    else:
        results.append(CheckResult("file_existence_and_load", True, "All video/audio paths exist and embeddings loaded"))

    if zero_len:
        results.append(CheckResult("embedding_nonempty", False, f"{zero_len} empty embedding arrays found"))
    else:
        results.append(CheckResult("embedding_nonempty", True, "All embeddings were non-empty"))

    if nonfinite:
        results.append(CheckResult("embedding_finite", False, f"{nonfinite} embeddings contained non-finite values"))
    else:
        results.append(CheckResult("embedding_finite", True, "All embeddings were finite"))

    if hidden_dim is None:
        results.append(CheckResult("embedding_shape", False, "No embeddings were loaded"))
    else:
        results.append(CheckResult("embedding_hidden_dim", True, f"Hidden dim inferred as {hidden_dim}; shapes observed={sorted(shapes)[:5]}"))

    fold_checks = verify_folds(fold_dir)
    results.extend(fold_checks)

    _print_summary(results)
    return 0 if all(r.ok for r in results) else 1


def verify_folds(fold_dir: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    if not fold_dir.exists():
        return [CheckResult("fold_dir_exists", False, f"Missing fold directory: {fold_dir}")]

    failures = []
    for fold_idx in range(5):
        train_path = fold_dir / f"meld_fold_{fold_idx}_train.csv"
        val_path = fold_dir / f"meld_fold_{fold_idx}_val.csv"
        if not train_path.exists() or not val_path.exists():
            failures.append(f"fold {fold_idx}: missing train/val CSV")
            continue
        train_df = pd.read_csv(train_path)
        val_df = pd.read_csv(val_path)
        train_ids = set(train_df["sample_id"].astype(str).tolist())
        val_ids = set(val_df["sample_id"].astype(str).tolist())
        if train_ids & val_ids:
            failures.append(f"fold {fold_idx}: sample_id overlap={len(train_ids & val_ids)}")
        train_dialogues = {infer_dialogue_key(sid) for sid in train_ids}
        val_dialogues = {infer_dialogue_key(sid) for sid in val_ids}
        dialogue_overlap = train_dialogues & val_dialogues
        if dialogue_overlap:
            failures.append(f"fold {fold_idx}: dialogue overlap={len(dialogue_overlap)}")
        if not train_df.empty and not val_df.empty:
            results.append(
                CheckResult(
                    f"fold_{fold_idx}_counts",
                    True,
                    f"train_rows={len(train_df)}, val_rows={len(val_df)}, dialogue_overlap=0",
                )
            )
    if failures:
        results.append(CheckResult("fold_integrity", False, "; ".join(failures)))
    else:
        results.append(CheckResult("fold_integrity", True, f"All 5 folds present and dialogue-safe in {fold_dir}"))
    return results


def _print_summary(results: list[CheckResult]) -> None:
    print("MELD ViT facial-cue pipeline verification")
    print("=" * 50)
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")
    passed = sum(1 for r in results if r.ok)
    failed = len(results) - passed
    print("-" * 50)
    print(f"Summary: {passed} passed, {failed} failed")


if __name__ == "__main__":
    raise SystemExit(main())
