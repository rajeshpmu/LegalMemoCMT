#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


#DEFAULT_DIR = Path("data/processed/MELD_VIT_FACECUE/train/video")
DEFAULT_DIR = Path("data/processed/MELD_VIT_FACECROP/train/video")


def pick_file(directory: Path, file_path: str | None, index: int) -> Path:
    if file_path:
        chosen = Path(file_path)
        if not chosen.is_absolute():
            chosen = directory / chosen
        return chosen

    files = sorted(directory.glob("*.npy"))
    if not files:
        raise FileNotFoundError(f"No .npy files found in {directory}")
    if index < 0 or index >= len(files):
        raise IndexError(f"index {index} is out of range for {len(files)} files")
    return files[index]


def describe_array(arr: np.ndarray) -> None:
    arr = np.asarray(arr)
    print(f"shape: {arr.shape}")
    print(f"dtype: {arr.dtype}")
    print(f"ndim: {arr.ndim}")
    print(f"size: {arr.size}")
    if arr.size == 0:
        print("array is empty")
        return
    finite = np.isfinite(arr)
    print(f"finite_values: {int(finite.sum())}/{arr.size}")
    print(f"min: {float(np.min(arr)):.6f}")
    print(f"max: {float(np.max(arr)):.6f}")
    print(f"mean: {float(np.mean(arr)):.6f}")
    print(f"std: {float(np.std(arr)):.6f}")

    if arr.ndim == 2:
        rows, cols = arr.shape
        print(f"rows: {rows}")
        print(f"feature_dim: {cols}")
        print("first_frame_first_8_values:")
        print(np.array2string(arr[0, :8], precision=5, suppress_small=False))
        if rows > 1:
            print("second_frame_first_8_values:")
            print(np.array2string(arr[1, :8], precision=5, suppress_small=False))
    elif arr.ndim == 1:
        print("first_12_values:")
        print(np.array2string(arr[:12], precision=5, suppress_small=False))
    else:
        flat = arr.reshape(-1)
        print("first_12_values:")
        print(np.array2string(flat[:12], precision=5, suppress_small=False))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load and inspect one MELD ViT facial-cue .npy file"
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help=f"Directory containing .npy files (default: {DEFAULT_DIR})",
    )
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Optional file name or path to inspect instead of auto-picking the first file",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="Index of the .npy file to pick when --file is not provided",
    )
    args = parser.parse_args()

    directory = args.dir
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    path = pick_file(directory, args.file or None, args.index)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() != ".npy":
        raise ValueError(f"Expected a .npy file, got: {path}")

    print(f"file: {path}")
    arr = np.load(path, allow_pickle=False)
    describe_array(arr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
