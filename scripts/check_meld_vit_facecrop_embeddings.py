#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify MELD face-crop embeddings before training on RunPod")
    parser.add_argument("--manifest", type=str, default="data/manifests/meld_vit_facecrop_control_cv/meld_fold_4_train.csv")
    parser.add_argument("--expected-feature-dim", type=int, default=768)
    parser.add_argument("--expected-rows", type=int, default=0)
    parser.add_argument("--max-samples", type=int, default=3)
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest}")

    df = pd.read_csv(manifest)
    if args.expected_rows and len(df) != args.expected_rows:
        raise ValueError(f"Unexpected manifest row count: got {len(df)}, expected {args.expected_rows}")
    if df.empty:
        raise ValueError("Manifest is empty")
    if "video_path" not in df.columns:
        raise ValueError("Manifest does not contain a video_path column")

    observed_shapes: set[tuple[int, ...]] = set()
    for i, path_str in enumerate(df["video_path"].head(max(1, args.max_samples))):
        path = Path(str(path_str))
        if not path.exists():
            raise FileNotFoundError(f"Missing embedding file: {path}")
        arr = np.load(path, allow_pickle=False, mmap_mode="r")
        observed_shapes.add(tuple(arr.shape))
        if arr.ndim != 2:
            raise ValueError(f"Expected 2D embedding array, got shape {arr.shape} at {path}")
        if arr.shape[-1] != args.expected_feature_dim:
            raise ValueError(
                f"Embedding dim mismatch at {path}: got {arr.shape[-1]}, expected {args.expected_feature_dim}"
            )
        if not np.isfinite(arr).all():
            raise ValueError(f"Non-finite values found in {path}")

    print("MELD face-crop embedding verification")
    print(f"Manifest: {manifest}")
    print(f"Rows: {len(df)}")
    print(f"Observed shapes: {sorted(observed_shapes)}")
    print(f"Expected feature dim: {args.expected_feature_dim}")
    print("Status: PASS")


if __name__ == "__main__":
    main()
