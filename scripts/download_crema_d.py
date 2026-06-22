from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent


CREMA_D_URL = "https://github.com/CheyneyComputerScience/CREMA-D"
CREMA_D_MIRROR_URL = "https://gitlab.com/cs-cooper-lab/crema-d-mirror.git"


README_TEXT = dedent(
    f"""
    CREMA-D setup
    =============

    Official repository:
      {CREMA_D_URL}

    Mirror repository:
      {CREMA_D_MIRROR_URL}

    Access notes:
    - CREMA-D is public and available through GitHub or the GitLab mirror.
    - The repository uses Git Large File Storage (git-lfs).
    - If you download the ZIP archive, the media files may remain as LFS pointers.
    - Recommended access method: git lfs clone from the official repo or mirror.

    Suggested workflow for this project:
    1. Clone the repository into this workspace.
    2. Copy or link the AudioWAV / AudioMP3 / VideoFlash folders into the local data area.
    3. Export a CSV with columns:
         sample_id, split, label, transcript, video_path, audio_path
    4. Run scripts/build_crema_d_manifest.py to produce the manifest.
    """
).strip() + "\n"


CSV_TEMPLATE = dedent(
    """
    sample_id,split,label,transcript,video_path,audio_path
    """
).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare CREMA-D workspace and access notes")
    parser.add_argument("--output", type=str, default="data/CREMA_D", help="Local CREMA-D workspace")
    parser.add_argument("--write-template", action="store_true", help="Write a manifest template CSV")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print("CREMA-D is the recommended public replacement benchmark for the deferred IEMOCAP slot.")
    print(f"Official repository: {CREMA_D_URL}")
    print(f"Mirror repository: {CREMA_D_MIRROR_URL}")
    print(f"Local workspace: {out}")
    print("Recommended access method: git lfs clone rather than ZIP download.")

    (out / "README.txt").write_text(README_TEXT, encoding="utf-8")
    for subdir in ["raw", "processed", "features", "annotations"]:
        (out / subdir).mkdir(parents=True, exist_ok=True)

    if args.write_template:
        (out / "labels.csv").write_text(CSV_TEMPLATE, encoding="utf-8")
        print(f"Wrote template CSV: {out / 'labels.csv'}")
        print("Fill the template with real CREMA-D rows before building the manifest.")


if __name__ == "__main__":
    main()
