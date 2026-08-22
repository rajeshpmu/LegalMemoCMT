from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.trimodal_validation_utils import (
        SUMMARY_OUTPUT,
        WITNESS_VALIDATED,
        count_utterances,
        csv_rows,
        csv_write,
        extract_transcript_text,
        normalize_case_number,
        normalize_text,
    )
else:
    from .trimodal_validation_utils import (
        SUMMARY_OUTPUT,
        WITNESS_VALIDATED,
        count_utterances,
        csv_rows,
        csv_write,
        extract_transcript_text,
        normalize_case_number,
        normalize_text,
    )


EXTRA_COLUMNS = [
    "transcript_speaker_turns",
    "witness_utterance_count",
    "counsel_utterance_count",
    "judge_utterance_count",
    "estimated_utterance_count",
]


def _summary_base() -> dict[str, object]:
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
    parser = argparse.ArgumentParser(description="Estimate utterance counts from validated transcripts")
    parser.add_argument("--witness-input", default=str(WITNESS_VALIDATED))
    parser.add_argument("--witness-output", default=str(WITNESS_VALIDATED))
    parser.add_argument("--summary-output", default=str(SUMMARY_OUTPUT))
    args = parser.parse_args()

    rows = csv_rows(args.witness_input)
    out_rows: list[dict[str, object]] = []
    distinct_witnesses: set[str] = set()
    cases: set[str] = set()
    public = protected = unresolved = non_witness = 0
    final_yes = 0
    hours = 0.0
    estimated_utterances = 0
    witness_utterances = 0

    for row in rows:
        base = dict(row)
        transcript_path_text = normalize_text(row.get("local_transcript_path"))
        transcript_path = Path(transcript_path_text) if transcript_path_text else None
        counts = {"total": 0, "witness": 0, "counsel": 0, "judge": 0}
        if transcript_path is not None and transcript_path.exists() and transcript_path.is_file():
            text, _page_count = extract_transcript_text(transcript_path)
            counts = count_utterances(text)
        base.update(
            {
                "transcript_speaker_turns": counts["total"],
                "witness_utterance_count": counts["witness"],
                "counsel_utterance_count": counts["counsel"],
                "judge_utterance_count": counts["judge"],
                "estimated_utterance_count": counts["total"],
            }
        )
        out_rows.append(base)

        if row.get("pilot_selected") != "YES":
            continue
        estimated_utterances += counts["total"]
        witness_utterances += counts["witness"]
        if row.get("final_trimodal_eligible") == "YES":
            final_yes += 1
        cases.add(normalize_case_number(row.get("case_number")))
        hours += float(row.get("probed_duration_seconds") or 0) / 3600.0
        status = normalize_text(row.get("witness_identity_status"))
        witness_value = normalize_text(row.get("witness_name_or_code"))
        if status == "PUBLIC_NAME":
            public += 1
            if witness_value:
                distinct_witnesses.add(witness_value)
        elif status == "PROTECTED_CODE":
            protected += 1
            if witness_value:
                distinct_witnesses.add(witness_value)
        elif status == "NO_WITNESS_TESTIMONY":
            non_witness += 1
        else:
            unresolved += 1

    csv_write(args.witness_output, out_rows, list(rows[0].keys()) + [c for c in EXTRA_COLUMNS if c not in rows[0].keys()])

    summary = _summary_base()
    summary.update(
        {
            "paired_hearings_input": sum(1 for row in rows if normalize_text(row.get("pairing_status")) == "paired"),
            "media_validated_hearings": sum(1 for row in rows if row.get("pilot_selected") == "YES" and row.get("media_validation_status") == "validated"),
            "transcript_validated_hearings": sum(1 for row in rows if row.get("pilot_selected") == "YES" and row.get("transcript_validation_status") == "validated"),
            "final_trimodal_eligible_hearings": final_yes,
            "verified_video_hours": round(hours, 2),
            "public_witnesses": public,
            "protected_witnesses": protected,
            "distinct_witnesses": len(distinct_witnesses),
            "unresolved_witness_hearings": unresolved,
            "non_witness_hearings": non_witness,
            "duplicate_media_count": sum(1 for row in rows if row.get("pilot_selected") == "YES" and row.get("duplicate_media") == "YES"),
            "estimated_utterances": estimated_utterances,
            "witness_utterances": witness_utterances,
            "cases_represented": len(cases),
        }
    )
    Path(args.summary_output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote summary to {args.summary_output}")


if __name__ == "__main__":
    main()
