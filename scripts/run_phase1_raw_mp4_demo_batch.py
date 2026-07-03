#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SINGLE_SCRIPT = PROJECT_ROOT / "scripts" / "run_phase1_raw_mp4_demo.sh"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the raw-mp4 demo on multiple clips one after another.")
    parser.add_argument("--pairs-csv", required=True, help="CSV with columns sample_id,video_path")
    parser.add_argument("--manifest", default="data/manifests/meld_test.csv", help="Manifest CSV")
    parser.add_argument("--checkpoint", default="results/paper_aligned_meld_cv/cmt_min/fold_2/best_model.pt", help="Checkpoint")
    parser.add_argument("--device", default="cpu", help="cpu, cuda, mps, or auto")
    parser.add_argument("--vision-mode", default="facecrop", choices=["facecrop", "fullframe"])
    parser.add_argument("--modalities", default="text,audio,video")
    parser.add_argument("--fusion-pooling", default="")
    parser.add_argument("--fusion-mode", default="")
    parser.add_argument("--encoder-mode", default="")
    parser.add_argument("--cache-dir", default="results/phase1_review_demo/raw_mp4_cache")
    parser.add_argument("--output-dir", default="results/phase1_review_demo/raw_mp4_batch")
    parser.add_argument("--vit-batch-size", type=int, default=8)
    args = parser.parse_args()

    pairs_path = Path(args.pairs_csv)
    if not pairs_path.exists():
        raise FileNotFoundError(f"Missing pairs CSV: {pairs_path}")
    if not SINGLE_SCRIPT.exists():
        raise FileNotFoundError(f"Missing single-demo script: {SINGLE_SCRIPT}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.csv"

    rows = list(csv.DictReader(pairs_path.open("r", encoding="utf-8", newline="")))
    if not rows:
        raise ValueError(f"{pairs_path} does not contain any rows")
    if "sample_id" not in rows[0] or "video_path" not in rows[0]:
        raise ValueError("pairs CSV must contain sample_id and video_path columns")

    summary_rows = []
    for row in rows:
        sample_id = row["sample_id"].strip()
        video_path = row["video_path"].strip()
        if not sample_id or not video_path:
            continue
        log_path = log_dir / f"{sample_id}.txt"
        cmd = [
            str(SINGLE_SCRIPT),
            sample_id,
            video_path,
        ]
        env = os.environ.copy()
        env.update(
            {
                "MANIFEST": args.manifest,
                "CHECKPOINT": args.checkpoint,
                "DEVICE": args.device,
                "VISION_MODE": args.vision_mode,
                "MODALITIES": args.modalities,
                "CACHE_DIR": args.cache_dir,
                "PYTHON_BIN": sys.executable,
            }
        )
        if args.fusion_pooling:
            env["FUSION_POOLING"] = args.fusion_pooling
        if args.fusion_mode:
            env["FUSION_MODE"] = args.fusion_mode
        if args.encoder_mode:
            env["ENCODER_MODE"] = args.encoder_mode
        print(f"Running {sample_id} -> {video_path}")
        result = subprocess.run(
            ["bash", str(SINGLE_SCRIPT), sample_id, video_path],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        log_path.write_text(result.stdout + ("\n" + result.stderr if result.stderr else ""), encoding="utf-8")
        success = result.returncode == 0
        summary_rows.append(
            {
                "sample_id": sample_id,
                "video_path": video_path,
                "returncode": result.returncode,
                "status": "ok" if success else "failed",
                "log_path": str(log_path),
            }
        )
        print(f"  status: {'ok' if success else 'failed'}")
        if not success:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)

    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sample_id", "video_path", "returncode", "status", "log_path"])
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Wrote batch summary to {summary_path}")


if __name__ == "__main__":
    main()
