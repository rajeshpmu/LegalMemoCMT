"""Run the Pyannote 4-compatible Tupac diarizer by source in parallel."""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", required=True)
    p.add_argument("--output-csv", required=True)
    p.add_argument("--segments-csv", required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    p.add_argument("--model", default="pyannote/speaker-diarization-3.1")
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    python_bin = os.environ.get("PYTHON_BIN", "python3")
    rows = pd.read_csv(args.input_csv, dtype=str).fillna("").to_dict("records")
    source_col = "source_audio_path" if "source_audio_path" in rows[0] else "audio_path"
    sources = list(dict.fromkeys(r[source_col] for r in rows if r[source_col]))
    existing = pd.read_csv(args.segments_csv, dtype=str).fillna("").to_dict("records") if Path(args.segments_csv).exists() else []
    completed = {r.get("source_audio_path", "") for r in existing if r.get("source_audio_path")}
    pending = [s for s in sources if s not in completed]
    if not pending:
        subprocess.run([python_bin, str(root / "diarize_tupac_sources_pyannote4.py"), "--input-csv", args.input_csv, "--output-csv", args.output_csv, "--segments-csv", args.segments_csv, "--model", args.model, "--device", args.device, "--skip-completed"], check=True)
        return
    workers = max(1, min(args.workers, len(pending)))
    chunks = [pending[i::workers] for i in range(workers)]
    with tempfile.TemporaryDirectory(prefix="tupac_diarization_pyannote4_") as temp:
        temp_path = Path(temp)
        processes = []
        for i, chunk in enumerate(chunks):
            subset = [r for r in rows if r[source_col] in set(chunk)]
            input_path = temp_path / f"input_{i}.csv"
            write_rows(input_path, subset)
            command = [python_bin, str(root / "diarize_tupac_sources_pyannote4.py"), "--input-csv", str(input_path), "--output-csv", str(temp_path / f"output_{i}.csv"), "--segments-csv", str(temp_path / f"segments_{i}.csv"), "--model", args.model, "--device", args.device]
            print(f"Starting Tupac Pyannote 4 worker {i + 1}/{workers}: {len(chunk)} source(s)")
            processes.append(subprocess.Popen(command))
        statuses = [proc.wait() for proc in processes]
        if any(status != 0 for status in statuses):
            raise SystemExit(f"Pyannote 4 workers failed: statuses={statuses}")
        all_segments = list(existing)
        for i in range(workers):
            all_segments.extend(pd.read_csv(temp_path / f"segments_{i}.csv", dtype=str).fillna("").to_dict("records"))
        segment_df = pd.DataFrame(all_segments).drop_duplicates(subset=["source_audio_path", "speaker_cluster_id", "segment_start_seconds", "segment_end_seconds"])
        Path(args.segments_csv).parent.mkdir(parents=True, exist_ok=True)
        segment_df.to_csv(args.segments_csv, index=False)
    subprocess.run([python_bin, str(root / "diarize_tupac_sources_pyannote4.py"), "--input-csv", args.input_csv, "--output-csv", args.output_csv, "--segments-csv", args.segments_csv, "--model", args.model, "--device", args.device, "--skip-completed"], check=True)
    output = pd.read_csv(args.output_csv, dtype=str)
    segment_df = pd.read_csv(args.segments_csv, dtype=str)
    print(f"Pyannote 4 Tupac diarization complete: {len(output)} rows, {len(segment_df)} segments, workers={workers}")


if __name__ == "__main__":
    main()
