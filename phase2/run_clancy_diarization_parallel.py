from __future__ import annotations

import argparse
import csv
import os
import subprocess
import tempfile
from pathlib import Path


SEGMENT_COLUMNS = [
    "source_audio_path",
    "speaker_cluster_id",
    "segment_start_seconds",
    "segment_end_seconds",
    "diarization_model",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Clancy diarization in bounded source-level parallel workers")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--segments-csv", required=True)
    parser.add_argument("--workers", type=int, default=0, help="Workers; auto uses 2 on CPU and 1 on MPS/CUDA")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--model", default="pyannote/speaker-diarization-3.1")
    parser.add_argument("--min-speakers", type=int, default=0)
    parser.add_argument("--max-speakers", type=int, default=0)
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    segments_path = Path(args.segments_csv)
    rows = read_csv(input_path)
    source_col = "source_audio_path" if "source_audio_path" in rows[0] else "audio_path"
    sources = list(dict.fromkeys(row.get(source_col, "") for row in rows if row.get(source_col, "")))

    existing_segments = read_csv(segments_path) if segments_path.exists() else []
    completed = {
        row.get("source_audio_path", "")
        for row in existing_segments
        if row.get("source_audio_path", "")
    }
    pending = [source for source in sources if source not in completed]
    if not pending:
        print(f"No pending sources. Reusing {len(completed)} completed sources.")
        subprocess.run([
            os.environ.get("PYTHON_BIN", "python3"),
            "phase2/diarize_clancy_sources.py",
            "--input-csv", str(input_path),
            "--output-csv", str(args.output_csv),
            "--segments-csv", str(segments_path),
            "--model", args.model,
            "--device", args.device,
            "--skip-completed",
        ], check=True)
        return

    workers = args.workers or (1 if args.device != "cpu" else 2)
    workers = max(1, min(workers, len(pending)))
    chunks = [pending[index::workers] for index in range(workers)]
    python_bin = os.environ.get("PYTHON_BIN", "python3")

    with tempfile.TemporaryDirectory(prefix="clancy_diarization_") as temp_dir:
        temp_root = Path(temp_dir)
        processes: list[subprocess.Popen[bytes]] = []
        for worker_id, chunk in enumerate(chunks):
            source_set = set(chunk)
            subset_rows = [row for row in rows if row.get(source_col, "") in source_set]
            subset_input = temp_root / f"input_{worker_id}.csv"
            subset_output = temp_root / f"output_{worker_id}.csv"
            subset_segments = temp_root / f"segments_{worker_id}.csv"
            write_csv(subset_input, subset_rows, list(rows[0].keys()))
            command = [
                python_bin,
                "phase2/diarize_clancy_sources.py",
                "--input-csv", str(subset_input),
                "--output-csv", str(subset_output),
                "--segments-csv", str(subset_segments),
                "--model", args.model,
                "--device", args.device,
            ]
            if args.min_speakers > 0:
                command += ["--min-speakers", str(args.min_speakers)]
            if args.max_speakers > 0:
                command += ["--max-speakers", str(args.max_speakers)]
            print(f"Starting worker {worker_id + 1}/{workers}: {len(chunk)} source(s)")
            processes.append(subprocess.Popen(command))

        statuses = [process.wait() for process in processes]
        if any(status != 0 for status in statuses):
            raise SystemExit(f"At least one diarization worker failed: statuses={statuses}")

        merged_segments = list(existing_segments)
        for worker_id in range(workers):
            worker_segments = read_csv(temp_root / f"segments_{worker_id}.csv")
            merged_segments.extend(worker_segments)
        deduped = {}
        for row in merged_segments:
            key = tuple(row.get(column, "") for column in SEGMENT_COLUMNS[:4])
            deduped[key] = row
        write_csv(segments_path, list(deduped.values()), SEGMENT_COLUMNS)

    subprocess.run([
        python_bin,
        "phase2/diarize_clancy_sources.py",
        "--input-csv", str(input_path),
        "--output-csv", str(args.output_csv),
        "--segments-csv", str(segments_path),
        "--model", args.model,
        "--device", args.device,
        "--skip-completed",
    ], check=True)
    print(f"Parallel diarization complete: reused={len(completed)} new={len(pending)} workers={workers}")


if __name__ == "__main__":
    main()
