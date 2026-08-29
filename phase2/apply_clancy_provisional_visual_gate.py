"""Add a clearly marked provisional visual gate to accepted Clancy rows.

This does not perform visual inspection. It records the user's temporary
assumption in a derived manifest so the original accepted file is preserved.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-csv",
        default="data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_usable.csv",
    )
    parser.add_argument(
        "--output-csv",
        default="data/processed/phase2/clancy/witness_only_v10/clancy_witness_speaking_usable_visual_provisional.csv",
    )
    parser.add_argument("--verification-status", default="PROVISIONAL_NOT_HUMAN_VERIFIED")
    parser.add_argument("--verification-source", default="user_provisional_assumption")
    parser.add_argument("--verification-confidence", default="HIGH")
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"No rows found in {args.input_csv}")

    extra_fields = [
        "speaker_visible_during_speech",
        "face_visible_ratio",
        "visual_verification_confidence",
        "visual_verification_source",
        "visual_verification_status",
    ]
    fields = list(rows[0])
    for field in extra_fields:
        if field not in fields:
            fields.append(field)

    for row in rows:
        row["visual_speaker_match"] = "YES"
        row["speaker_visible_during_speech"] = "YES"
        row["face_visible_ratio"] = "0.60"
        row["visual_verification_confidence"] = args.verification_confidence
        row["visual_verification_source"] = args.verification_source
        row["visual_verification_status"] = args.verification_status

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} visual-gate rows to {output}")
    if args.verification_status != "HUMAN_VERIFIED":
        print("WARNING: visual values are assumptions and are not human video verification.")


if __name__ == "__main__":
    main()
