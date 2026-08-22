from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def check_file_signature(path: Path) -> tuple[bool, str]:
    file_bin = shutil.which("file")
    if file_bin is not None:
        try:
            out = subprocess.run([file_bin, str(path)], check=True, capture_output=True, text=True).stdout.strip()
            if "ISO Media" in out or "MP4" in out:
                return True, out
            return False, out or "unexpected file type"
        except subprocess.CalledProcessError as exc:
            msg = (exc.stdout or exc.stderr or "").strip()
            return False, msg or "file command failed"

    try:
        with path.open("rb") as f:
            header = f.read(128)
        if b"ftyp" in header[:64]:
            return True, "mp4 signature detected"
        return False, "file command missing and MP4 signature not detected"
    except Exception as exc:
        return False, str(exc)


def check_ffprobe(path: Path) -> tuple[bool, str]:
    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin is None:
        return False, "ffprobe missing"
    try:
        out = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_streams", "-show_format", str(path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return True, out or "ok"
    except subprocess.CalledProcessError as exc:
        msg = (exc.stdout or exc.stderr or "").strip()
        return False, msg or "ffprobe failed"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate MP4 files when ffprobe is unavailable.")
    parser.add_argument("paths", nargs="+", help="One or more media files to validate")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    results: list[dict[str, object]] = []
    all_ok = True

    for item in args.paths:
        path = Path(item)
        exists = path.exists()
        file_ok, file_msg = check_file_signature(path) if exists else (False, "missing")
        probe_ok, probe_msg = check_ffprobe(path) if exists and file_ok else (False, "skipped")
        ok = exists and file_ok and (probe_ok or probe_msg == "ffprobe missing")
        all_ok = all_ok and ok
        results.append(
            {
                "path": str(path),
                "exists": exists,
                "file_ok": file_ok,
                "file_message": file_msg,
                "ffprobe_ok": probe_ok,
                "ffprobe_message": probe_msg,
                "status": "PASS" if ok else "FAIL",
            }
        )

    payload = {"overall_status": "PASS" if all_ok else "FAIL", "results": results}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for row in results:
            print(f"{row['status']} {row['path']}")
            print(f"  file: {row['file_message']}")
            print(f"  ffprobe: {row['ffprobe_message']}")
        print(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")

    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
