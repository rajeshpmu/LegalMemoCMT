from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent


MSP_IMPROV_URL = "https://www.lab-msp.com/MSP/MSP-Improv.html"
MSP_IMPROV_LICENSE_URL = "https://www.lab-msp.com/MSP/publications/AcademicLicense-MSP-IMPROV.pdf"


README_TEXT = dedent(
    f"""
    MSP-IMPROV setup
    =================

    Official corpus page:
      {MSP_IMPROV_URL}

    Academic license form:
      {MSP_IMPROV_LICENSE_URL}

    Access notes:
    - MSP-IMPROV is available under an academic license.
    - The license form needs to be signed by the director of the research group.
    - The lab asks you to use your institution email and copy the group leader or laboratory director.

    Recommended workflow for this project:
    1. Request access to MSP-IMPROV using the official license process.
    2. Download/extract the corpus into this workspace.
    3. Export metadata to a CSV with columns:
         sample_id, split, label, transcript, video_path, audio_path
    4. Run scripts/build_msp_improv_manifest.py to create a processed manifest.
    """
).strip() + "\n"


CSV_TEMPLATE = dedent(
    """
    sample_id,split,label,transcript,video_path,audio_path
    """
).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare MSP-IMPROV workspace and access notes")
    parser.add_argument("--output", type=str, default="data/MSP_IMPROV", help="Local MSP-IMPROV workspace")
    parser.add_argument("--write-template", action="store_true", help="Write a manifest template CSV")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    print("MSP-IMPROV is the recommended emotion-focused replacement for IEMOCAP in this project.")
    print(f"Official corpus page: {MSP_IMPROV_URL}")
    print(f"Academic license form: {MSP_IMPROV_LICENSE_URL}")
    print(f"Local workspace: {out}")

    (out / "README.txt").write_text(README_TEXT, encoding="utf-8")
    for subdir in ["raw", "processed", "features", "annotations"]:
        (out / subdir).mkdir(parents=True, exist_ok=True)

    if args.write_template:
        (out / "labels.csv").write_text(CSV_TEMPLATE, encoding="utf-8")
        print(f"Wrote template CSV: {out / 'labels.csv'}")
        print("Fill the template with real MSP-IMPROV rows before building the manifest.")


if __name__ == "__main__":
    main()
