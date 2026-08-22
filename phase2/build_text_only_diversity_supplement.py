from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir
    from phase2.trimodal_validation_utils import (
        csv_rows,
        csv_write,
        count_utterances,
        extract_transcript_text,
        normalize_case_number,
        normalize_text,
    )
else:
    from .common import ensure_dir
    from .trimodal_validation_utils import (
        csv_rows,
        csv_write,
        count_utterances,
        extract_transcript_text,
        normalize_case_number,
        normalize_text,
    )


HEARING_VALIDATED_INPUT = Path("data/processed/phase2/hearing_manifest_validated.csv")
OUTPUT_CSV = Path("data/processed/phase2/text_only_diversity_supplement.csv")
SUMMARY_OUTPUT = Path("reports/phase2/text_only_diversity_supplement_summary.json")

TARGET_CASE_ORDER = ["IT-09-92", "IT-05-88", "IT-04-81"]
TARGET_QUOTAS = {
    "IT-09-92": 2,
    "IT-05-88": 2,
    "IT-04-81": 1,
}


def _load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return csv_rows(path)


def _score(row: dict[str, object]) -> float:
    utterances = float(row.get("estimated_utterance_count") or 0)
    witness = float(row.get("witness_utterance_count") or 0)
    counsel = float(row.get("counsel_utterance_count") or 0)
    judge = float(row.get("judge_utterance_count") or 0)
    score = utterances + witness * 0.5 + min(counsel, 200.0) * 0.05 + min(judge, 100.0) * 0.05
    if row.get("witness_testimony_present") == "YES":
        score += 25
    if row.get("witness_identity_status") in {"PUBLIC_NAME", "PROTECTED_CODE"}:
        score += 10
    return round(score, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a modest text-only diversity supplement from transcript-only hearings")
    parser.add_argument("--hearing-input", default=str(HEARING_VALIDATED_INPUT))
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV))
    parser.add_argument("--summary-output", default=str(SUMMARY_OUTPUT))
    args = parser.parse_args()

    hearing_rows = _load_rows(Path(args.hearing_input))
    candidates: list[dict[str, object]] = []
    for row in hearing_rows:
        if normalize_text(row.get("pairing_status")) != "transcript_only":
            continue
        if normalize_text(row.get("transcript_readable")).upper() != "YES":
            continue
        transcript_path_text = normalize_text(row.get("local_transcript_path"))
        transcript_path = Path(transcript_path_text) if transcript_path_text else None
        if transcript_path is None or not transcript_path.exists() or not transcript_path.is_file():
            continue
        text, _page_count = extract_transcript_text(transcript_path)
        counts = count_utterances(text)
        if counts["total"] <= 0:
            continue
        if counts["witness"] <= 0 and counts["total"] < 100:
            continue
        record = {
            **row,
            "transcript_speaker_turns": counts["total"],
            "witness_utterance_count": counts["witness"],
            "counsel_utterance_count": counts["counsel"],
            "judge_utterance_count": counts["judge"],
            "estimated_utterance_count": counts["total"],
            "selection_mode": "TEXT_ONLY_DIVERSITY_SUPPLEMENT",
            "selection_reason": "modest_case_diversity",
            "selection_score": _score(
                {
                    **row,
                    "transcript_speaker_turns": counts["total"],
                    "witness_utterance_count": counts["witness"],
                    "counsel_utterance_count": counts["counsel"],
                    "judge_utterance_count": counts["judge"],
                    "estimated_utterance_count": counts["total"],
                    "witness_testimony_present": "YES" if counts["witness"] > 0 else "NO",
                }
            ),
        }
        candidates.append(record)

    by_case: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in candidates:
        by_case[normalize_case_number(row.get("case_number"))].append(row)

    selected: list[dict[str, object]] = []
    for case_number in TARGET_CASE_ORDER:
        rows = sorted(
            by_case.get(case_number, []),
            key=lambda row: (
                -float(row.get("selection_score") or 0),
                normalize_text(row.get("hearing_date")),
                normalize_text(row.get("record_title")),
            ),
        )
        quota = TARGET_QUOTAS.get(case_number, 0)
        selected.extend(rows[:quota])

    selected.sort(
        key=lambda row: (
            TARGET_CASE_ORDER.index(normalize_case_number(row.get("case_number"))) if normalize_case_number(row.get("case_number")) in TARGET_CASE_ORDER else 999,
            -float(row.get("selection_score") or 0),
            normalize_text(row.get("hearing_date")),
            normalize_text(row.get("record_title")),
        )
    )

    fieldnames = [
        "hearing_id",
        "tribunal",
        "case_family",
        "case_number",
        "hearing_date",
        "record_title",
        "pairing_status",
        "transcript_url",
        "witness_name_or_code",
        "witness_identity_status",
        "examination_type",
        "transcript_speaker_turns",
        "witness_utterance_count",
        "counsel_utterance_count",
        "judge_utterance_count",
        "estimated_utterance_count",
        "selection_mode",
        "selection_reason",
        "selection_score",
        "notes",
    ]
    csv_write(args.output_csv, selected, fieldnames)

    summary = {
        "selected_rows": len(selected),
        "case_numbers_selected": len({normalize_case_number(row.get("case_number")) for row in selected if normalize_case_number(row.get("case_number"))}),
        "case_families_selected": len({normalize_text(row.get("case_family")) for row in selected if normalize_text(row.get("case_family"))}),
        "estimated_utterances": sum(int(row.get("estimated_utterance_count") or 0) for row in selected),
        "witness_utterances": sum(int(row.get("witness_utterance_count") or 0) for row in selected),
        "counsel_utterances": sum(int(row.get("counsel_utterance_count") or 0) for row in selected),
        "judge_utterances": sum(int(row.get("judge_utterance_count") or 0) for row in selected),
        "cases": Counter(normalize_case_number(row.get("case_number")) for row in selected if normalize_case_number(row.get("case_number"))),
        "selection_mode": "text_only_diversity_supplement",
    }
    summary["cases"] = dict(summary["cases"])
    ensure_dir(Path(args.summary_output).parent)
    Path(args.summary_output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(selected)} text-only supplement rows to {args.output_csv}")
    print(f"Wrote summary to {args.summary_output}")


if __name__ == "__main__":
    main()
