from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.trimodal_validation_utils import (
        HEARING_VALIDATED,
        WITNESS_VALIDATED,
        csv_rows,
        csv_write,
        detect_examination_type,
        extract_witness_identity,
        extract_transcript_text,
        has_witness_testimony,
        normalize_text,
    )
else:
    from .trimodal_validation_utils import (
        HEARING_VALIDATED,
        WITNESS_VALIDATED,
        csv_rows,
        csv_write,
        detect_examination_type,
        extract_witness_identity,
        extract_transcript_text,
        has_witness_testimony,
        normalize_text,
    )


EXTRA_COLUMNS = [
    "witness_name_or_code",
    "witness_identity_status",
    "witness_type",
    "witness_resolution_source",
    "witness_resolution_confidence",
    "witness_testimony_present",
    "final_trimodal_eligible",
    "examination_type",
]


def _witness_type(status: str) -> str:
    if status == "PUBLIC_NAME":
        return "public_witness"
    if status == "PROTECTED_CODE":
        return "protected_witness"
    if status == "NO_WITNESS_TESTIMONY":
        return "non_witness"
    return "unresolved_witness"


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve witnesses from validated transcripts")
    parser.add_argument("--hearing-input", default=str(HEARING_VALIDATED))
    parser.add_argument("--witness-output", default=str(WITNESS_VALIDATED))
    args = parser.parse_args()

    rows = csv_rows(args.hearing_input)
    out_rows: list[dict[str, object]] = []
    for row in rows:
        base = dict(row)
        transcript_path_text = normalize_text(row.get("local_transcript_path"))
        transcript_path = Path(transcript_path_text) if transcript_path_text else None
        transcript_text = ""
        if transcript_path is not None and transcript_path.exists() and transcript_path.is_file():
            transcript_text, _page_count = extract_transcript_text(transcript_path)
        witness_name_or_code, identity_status, source, confidence = extract_witness_identity(
            transcript_text,
            title=normalize_text(row.get("record_title")),
        )
        if not witness_name_or_code:
            witness_name_or_code = "UNRESOLVED_WITNESS"
            identity_status = "UNRESOLVED_WITNESS"
        witness_testimony_present = "YES" if has_witness_testimony(transcript_text) else "NO"
        transcript_examination = detect_examination_type(transcript_text) if transcript_text else "unknown"
        final_trimodal_eligible = "YES" if (
            row.get("media_validation_status") == "validated"
            and row.get("transcript_validation_status") == "validated"
            and row.get("transcript_session_match") == "YES"
            and identity_status in {"PUBLIC_NAME", "PROTECTED_CODE"}
            and row.get("duplicate_media") != "YES"
            and row.get("video_playable") == "YES"
            and row.get("audio_present") == "YES"
            and float(row.get("probed_duration_seconds") or 0) > 0
            and witness_testimony_present == "YES"
        ) else "NO"
        base.update(
            {
                "witness_name_or_code": witness_name_or_code,
                "witness_identity_status": identity_status,
                "witness_type": _witness_type(identity_status),
                "witness_resolution_source": source,
                "witness_resolution_confidence": confidence,
                "witness_testimony_present": witness_testimony_present,
                "final_trimodal_eligible": final_trimodal_eligible,
                "examination_type": row.get("examination_type") or transcript_examination or "unknown",
            }
        )
        out_rows.append(base)

    fieldnames = list(rows[0].keys()) + [c for c in EXTRA_COLUMNS if c not in rows[0].keys()]
    csv_write(args.witness_output, out_rows, fieldnames)
    print(f"Wrote {len(out_rows)} witness rows to {args.witness_output}")


if __name__ == "__main__":
    main()
