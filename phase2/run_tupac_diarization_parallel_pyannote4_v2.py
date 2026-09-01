"""Robust Pyannote 4 Tupac coordinator with persistent worker diagnostics."""
from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

import pandas as pd


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", required=True)
    p.add_argument("--output-csv", required=True)
    p.add_argument("--segments-csv", required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    p.add_argument("--model", default="pyannote/speaker-diarization-3.1")
    p.add_argument("--work-dir", default="")
    args = p.parse_args()

    root = Path(__file__).resolve().parent
    python_bin = os.environ.get("PYTHON_BIN", "python3")
    input_path = Path(args.input_csv)
    segment_path = Path(args.segments_csv)
    rows = pd.read_csv(input_path, dtype=str).fillna("").to_dict("records")
    if not rows:
        raise SystemExit("Input CSV is empty")
    source_col = "source_audio_path" if "source_audio_path" in rows[0] else "audio_path"
    sources = list(dict.fromkeys(row[source_col] for row in rows if row[source_col]))
    existing = pd.read_csv(segment_path, dtype=str).fillna("").to_dict("records") if segment_path.exists() else []
    completed = {row.get("source_audio_path", "") for row in existing if row.get("source_audio_path")}
    pending = [source for source in sources if source not in completed]

    if not pending:
        subprocess.run([python_bin, str(root / "diarize_tupac_sources_pyannote4.py"), "--input-csv", str(input_path), "--output-csv", args.output_csv, "--segments-csv", str(segment_path), "--model", args.model, "--device", args.device, "--skip-completed"], check=True)
        return

    work = Path(args.work_dir) if args.work_dir else Path(args.output_csv).parent / f".tupac_diarization_pyannote4_{int(time.time())}"
    work.mkdir(parents=True, exist_ok=False)
    workers = max(1, min(args.workers, len(pending)))
    chunks = [pending[i::workers] for i in range(workers)]
    processes = []
    log_handles = []
    for i, chunk in enumerate(chunks):
        subset = [row for row in rows if row[source_col] in set(chunk)]
        subset_input = work / f"input_{i}.csv"
        pd.DataFrame(subset).to_csv(subset_input, index=False)
        stdout = (work / f"worker_{i}.stdout.log").open("w", encoding="utf-8")
        stderr = (work / f"worker_{i}.stderr.log").open("w", encoding="utf-8")
        log_handles.extend([stdout, stderr])
        command = [python_bin, str(root / "diarize_tupac_sources_pyannote4.py"), "--input-csv", str(subset_input), "--output-csv", str(work / f"output_{i}.csv"), "--segments-csv", str(work / f"segments_{i}.csv"), "--model", args.model, "--device", args.device]
        print(f"Starting Tupac Pyannote 4 worker {i + 1}/{workers}: {len(chunk)} source(s)")
        processes.append(subprocess.Popen(command, stdout=stdout, stderr=stderr))
    statuses = [proc.wait() for proc in processes]
    for handle in log_handles:
        handle.close()
    missing = []
    for i, status in enumerate(statuses):
        for kind in ("output", "segments"):
            path = work / f"{kind}_{i}.csv"
            if status != 0 or not path.exists():
                missing.append((i, status, str(path)))
    if missing:
        print(f"Worker artifacts missing or failed: {missing}")
        print(f"Persistent diagnostics: {work}")
        for i, _, _ in missing:
            log = work / f"worker_{i}.stderr.log"
            if log.exists():
                print(f"--- worker {i} stderr ---")
                print(log.read_text(encoding="utf-8", errors="replace")[-6000:])
        raise SystemExit(1)

    all_segments = list(existing)
    for i in range(workers):
        all_segments.extend(pd.read_csv(work / f"segments_{i}.csv", dtype=str).fillna("").to_dict("records"))
    segment_df = pd.DataFrame(all_segments).drop_duplicates(subset=["source_audio_path", "speaker_cluster_id", "segment_start_seconds", "segment_end_seconds"])
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    segment_df.to_csv(segment_path, index=False)
    subprocess.run([python_bin, str(root / "diarize_tupac_sources_pyannote4.py"), "--input-csv", str(input_path), "--output-csv", args.output_csv, "--segments-csv", str(segment_path), "--model", args.model, "--device", args.device, "--skip-completed"], check=True)
    output = pd.read_csv(args.output_csv, dtype=str)
    print(f"Pyannote 4 Tupac diarization complete: {len(output)} rows, {len(segment_df)} segments, workers={workers}")


if __name__ == "__main__":
    main()
