from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir
    from phase2.trimodal_validation_utils import (
        HEARING_INPUT,
        HEARING_VALIDATED,
        SUMMARY_OUTPUT,
        csv_rows,
        csv_write,
        detect_speaker_labels,
        extract_transcript_text,
        maybe_download_transcript,
        normalize_case_number,
        normalize_text,
        probe_media_url,
        select_pilot_rows,
        transcript_header_date,
    )
else:
    from .common import ensure_dir
    from .trimodal_validation_utils import (
        HEARING_INPUT,
        HEARING_VALIDATED,
        SUMMARY_OUTPUT,
        csv_rows,
        csv_write,
        detect_speaker_labels,
        extract_transcript_text,
        maybe_download_transcript,
        normalize_case_number,
        normalize_text,
        probe_media_url,
        select_pilot_rows,
        transcript_header_date,
    )


EXTRA_COLUMNS = [
    "validation_scope",
    "pilot_selected",
    "local_transcript_path",
    "media_validation_status",
    "probed_duration_seconds",
    "probed_duration_minutes",
    "video_playable",
    "audio_present",
    "video_codec",
    "audio_codec",
    "resolution",
    "frame_rate",
    "media_sha256",
    "duplicate_media",
    "transcript_readable",
    "transcript_session_match",
    "transcript_date_match",
    "transcript_validation_status",
    "transcript_page_count",
    "transcript_language",
    "speaker_labels",
    "transcript_header_date",
    "transcript_text_preview",
]


def _default_summary() -> dict[str, object]:
    return {
        "paired_hearings_input": 0,
        "media_validated_hearings": 0,
        "transcript_validated_hearings": 0,
        "final_trimodal_eligible_hearings": 0,
        "verified_video_hours": 0.0,
        "public_witnesses": 0,
        "protected_witnesses": 0,
        "distinct_witnesses": 0,
        "unresolved_witness_hearings": 0,
        "non_witness_hearings": 0,
        "duplicate_media_count": 0,
        "estimated_utterances": 0,
        "witness_utterances": 0,
        "cases_represented": 0,
        "target_video_hours": "20-30",
        "target_distinct_witnesses": "~50",
        "target_utterances": "10000-15000",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the tri-modal hearing manifest before full-scale download")
    parser.add_argument("--hearing-input", default=str(HEARING_INPUT))
    parser.add_argument("--hearing-output", default=str(HEARING_VALIDATED))
    parser.add_argument("--summary-output", default=str(SUMMARY_OUTPUT))
    parser.add_argument("--pilot-only", action="store_true", default=True, help="Process only the pilot subset")
    parser.add_argument("--all-paired", action="store_true", help="Process every paired hearing instead of only the pilot subset")
    args = parser.parse_args()

    rows = csv_rows(args.hearing_input)
    pilot_rows = select_pilot_rows(rows)
    pilot_ids = {normalize_text(row.get("hearing_id")) for row in pilot_rows}
    if args.all_paired:
        pilot_ids = {
            normalize_text(row.get("hearing_id"))
            for row in rows
            if normalize_text(row.get("pairing_status")) == "paired"
        }
    paired_input = sum(1 for row in rows if normalize_text(row.get("pairing_status")) == "paired")

    out_rows: list[dict[str, object]] = []
    duplicate_signatures: set[str] = set()
    seen_video_urls: set[str] = set()
    for row in rows:
        hearing_id = normalize_text(row.get("hearing_id"))
        selected = hearing_id in pilot_ids
        base = dict(row)
        base.setdefault("validation_scope", "pending")
        base.setdefault("pilot_selected", "NO")
        for col in EXTRA_COLUMNS:
            base.setdefault(col, "")
        if not selected:
            out_rows.append(base)
            continue

        video_url = normalize_text(row.get("video_url"))
        transcript_url = normalize_text(row.get("transcript_url"))
        media = probe_media_url(video_url)
        transcript_path = maybe_download_transcript(transcript_url, hearing_id, output_dir=Path(args.hearing_output).parent / "transcripts")
        transcript_text, transcript_pages = extract_transcript_text(transcript_path)
        transcript_date = transcript_header_date(transcript_text)
        speaker_labels = detect_speaker_labels(transcript_text)
        transcript_readable = "YES" if len(transcript_text.split()) >= 20 else "NO"
        transcript_date_match = "YES" if transcript_date and normalize_text(row.get("hearing_date")) == transcript_date else "NO"
        transcript_session_match = "YES" if transcript_date_match == "YES" else "NO"
        duplicate_media = "YES" if video_url and video_url in seen_video_urls else "NO"
        if video_url:
            seen_video_urls.add(video_url)
        media_sha256 = ""
        media_validation_status = media.status
        if duplicate_media == "YES":
            media_validation_status = "duplicate_media"
        if media.video_playable and media.audio_present and media.duration_seconds > 0 and duplicate_media == "NO":
            media_validation_status = "validated"

        base.update(
            {
                "validation_scope": "pilot" if not args.all_paired else "full",
                "pilot_selected": "YES",
                "local_transcript_path": str(transcript_path),
                "media_validation_status": media_validation_status,
                "probed_duration_seconds": f"{media.duration_seconds:.2f}" if media.duration_seconds else "0",
                "probed_duration_minutes": f"{media.duration_seconds / 60.0:.2f}" if media.duration_seconds else "0",
                "video_playable": "YES" if media.video_playable else "NO",
                "audio_present": "YES" if media.audio_present else "NO",
                "video_codec": media.video_codec,
                "audio_codec": media.audio_codec,
                "resolution": media.resolution,
                "frame_rate": media.frame_rate,
                "media_sha256": media_sha256,
                "duplicate_media": duplicate_media,
                "transcript_readable": transcript_readable,
                "transcript_session_match": transcript_session_match,
                "transcript_date_match": transcript_date_match,
                "transcript_validation_status": "validated" if transcript_readable == "YES" else "unreadable",
                "transcript_page_count": transcript_pages,
                "transcript_language": normalize_text(row.get("transcript_language") or row.get("video_language") or ""),
                "speaker_labels": "; ".join(speaker_labels[:12]),
                "transcript_header_date": transcript_date,
                "transcript_text_preview": normalize_text(transcript_text[:240]),
            }
        )
        out_rows.append(base)
        if duplicate_media == "YES":
            duplicate_signatures.add(video_url)

    fieldnames = list(rows[0].keys()) + [c for c in EXTRA_COLUMNS if c not in rows[0].keys()]
    ensure_dir(Path(args.hearing_output).parent)
    csv_write(args.hearing_output, out_rows, fieldnames)

    pilot_rows_validated = [row for row in out_rows if row.get("pilot_selected") == "YES"]
    summary = _default_summary()
    summary.update(
        {
            "paired_hearings_input": paired_input,
            "media_validated_hearings": sum(1 for row in pilot_rows_validated if row.get("media_validation_status") == "validated"),
            "transcript_validated_hearings": sum(1 for row in pilot_rows_validated if row.get("transcript_validation_status") == "validated"),
            "final_trimodal_eligible_hearings": 0,
            "verified_video_hours": round(
                sum(float(row.get("probed_duration_seconds") or 0) for row in pilot_rows_validated if row.get("media_validation_status") == "validated")
                / 3600.0,
                2,
            ),
            "duplicate_media_count": sum(1 for row in pilot_rows_validated if row.get("duplicate_media") == "YES"),
            "cases_represented": len({normalize_case_number(row.get("case_number")) for row in pilot_rows_validated}),
        }
    )
    ensure_dir(Path(args.summary_output).parent)
    Path(args.summary_output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(out_rows)} hearing rows to {args.hearing_output}")
    print(f"Wrote summary to {args.summary_output}")


if __name__ == "__main__":
    main()

