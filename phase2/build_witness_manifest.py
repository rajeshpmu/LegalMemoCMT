from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, sha1_short, write_csv
    from phase2.hearing_witness_manifest_utils import extract_witness_identity, normalize_whitespace
else:
    from .common import ensure_dir, read_csv_rows, sha1_short, write_csv
    from .hearing_witness_manifest_utils import extract_witness_identity, normalize_whitespace


OUTPUT_COLUMNS = [
    "manifest_id",
    "tribunal",
    "case_name",
    "case_number",
    "hearing_id",
    "hearing_date",
    "witness_name_or_code",
    "witness_type",
    "speaker_role",
    "examination_type",
    "transcript_url",
    "video_url",
    "expected_duration_minutes",
    "download_status",
    "annotation_status",
    "utterance_count",
    "emotion_label_status",
    "credibility_label_status",
    "source_record_id",
    "pairing_confidence",
    "eligible_for_trimodal_dataset",
    "notes",
]


def _witness_type(name_or_code: str, status: str) -> str:
    if status == "protected":
        return "protected_witness"
    if status == "public":
        return "public_witness"
    return "unresolved_witness"


def _manifest_id(hearing_id: str, witness_name_or_code: str, case_number: str) -> str:
    return f"wit_{sha1_short('|'.join([hearing_id, witness_name_or_code, case_number]), length=16)}"


def build_witness_manifest(hearing_manifest_csv: str | Path) -> list[dict[str, object]]:
    hearing_rows = read_csv_rows(Path(hearing_manifest_csv))
    out_rows: list[dict[str, object]] = []
    for row in hearing_rows:
        witness_name_or_code = normalize_whitespace(row.get("witness_name_or_code") or "")
        status = normalize_whitespace(row.get("witness_identity_status") or "").lower()
        if not witness_name_or_code:
            witness_name_or_code, status = extract_witness_identity(row.get("record_title") or "", row.get("case_family") or "")
        if not witness_name_or_code:
            witness_name_or_code = "UNRESOLVED_WITNESS"
            status = "unresolved"
        if witness_name_or_code != "UNRESOLVED_WITNESS" and status == "unresolved":
            status = "public"
        out_rows.append(
            {
                "manifest_id": _manifest_id(row.get("hearing_id") or "", witness_name_or_code, row.get("case_number") or ""),
                "tribunal": row.get("tribunal") or "",
                "case_name": row.get("case_family") or "",
                "case_number": row.get("case_number") or "",
                "hearing_id": row.get("hearing_id") or "",
                "hearing_date": row.get("hearing_date") or "",
                "witness_name_or_code": witness_name_or_code or "UNRESOLVED_WITNESS",
                "witness_type": _witness_type(witness_name_or_code, status),
                "speaker_role": "Witness",
                "examination_type": row.get("examination_type") or "unknown",
                "transcript_url": row.get("transcript_url") or "",
                "video_url": row.get("video_url") or "",
                "expected_duration_minutes": row.get("expected_duration_minutes") or "",
                "download_status": "resolved" if row.get("video_url") and row.get("transcript_url") else "partial",
                "annotation_status": "Not Started",
                "utterance_count": "",
                "emotion_label_status": "Pending",
                "credibility_label_status": "Pending",
                "source_record_id": row.get("tap_or_record_id") or "",
                "pairing_confidence": row.get("pairing_confidence") or "",
                "eligible_for_trimodal_dataset": row.get("eligible_for_trimodal_dataset") or "NO",
                "notes": row.get("notes") or "",
            }
        )

    out_rows.sort(key=lambda row: (row["tribunal"], row["case_number"], row["hearing_date"], row["witness_name_or_code"]))
    return out_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the resolved Phase 2 witness manifest from the hearing manifest")
    parser.add_argument("--hearing-manifest-csv", default="data/processed/phase2/hearing_manifest.csv")
    parser.add_argument(
        "--output-csv",
        default="data/phase2/source_manifests/witness_harvest_manifest_resolved.csv",
    )
    args = parser.parse_args()

    rows = build_witness_manifest(args.hearing_manifest_csv)
    ensure_dir(Path(args.output_csv).parent)
    write_csv(Path(args.output_csv), rows, OUTPUT_COLUMNS)
    print(f"Wrote {len(rows)} witness rows to {args.output_csv}")


if __name__ == "__main__":
    main()
