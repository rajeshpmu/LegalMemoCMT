from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent


MOSEI_SDK_URL = "http://sorena.multicomp.cs.cmu.edu/downloads/MOSEI"
MOSEI_RAW_URL = "http://sorena.multicomp.cs.cmu.edu/downloads_raw/MOSEI"


README_TEXT = dedent(
    f"""
    CMU-MOSEI setup
    =================

    This project now uses the official CMU Multimodal Data SDK workflow for MOSEI.

    Official dataset URL used by the SDK:
      {MOSEI_SDK_URL}

    Raw dataset URL referenced by the SDK:
      {MOSEI_RAW_URL}

    Recommended usage:
    1. Install the CMU Multimodal Data SDK.
    2. Use the SDK to fetch MOSEI features or align already downloaded files.
    3. Export a labels/metadata CSV with columns:
         video_id, segment_id, split, label, transcript, video_path, audio_path
    4. Run scripts/build_mosei_manifest.py against that CSV.
    5. The provided labels.csv template only contains the header row, so it must be filled before manifest building.

    Notes:
    - This script does not fake-download MOSEI.
    - It prepares the local folder structure and documents the SDK path.
    - If the SDK is already installed, you can use it to fetch aligned features.
    """
).strip() + "\n"


CSV_TEMPLATE = dedent(
    """
    video_id,segment_id,split,label,transcript,video_path,audio_path
    """
).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare CMU-MOSEI workspace using the official SDK path")
    parser.add_argument("--output", type=str, default="data/MOSEI", help="Local MOSEI workspace")
    parser.add_argument("--write-template", action="store_true", help="Write a labels.csv template")
    parser.add_argument("--print-only", action="store_true", help="Only print access guidance")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print("CMU-MOSEI should be accessed through the CMU Multimodal Data SDK.")
    print(f"SDK dataset URL: {MOSEI_SDK_URL}")
    print(f"Raw dataset URL: {MOSEI_RAW_URL}")
    print(f"Local workspace: {out}")
    print("This script prepares the workspace and guidance, not a direct dataset download.")

    (out / "README.txt").write_text(README_TEXT, encoding="utf-8")

    if args.write_template:
        (out / "labels.csv").write_text(CSV_TEMPLATE, encoding="utf-8")
        print(f"Wrote template CSV: {out / 'labels.csv'}")
        print("The template is a placeholder header only. Fill it with real MOSEI rows before building the manifest.")

    if not args.print_only:
        (out / "structure").mkdir(exist_ok=True)
        for subdir in ["raw", "processed", "features", "annotations"]:
            (out / subdir).mkdir(parents=True, exist_ok=True)
        print("Created standard MOSEI folders: raw, processed, features, annotations")


if __name__ == "__main__":
    main()
