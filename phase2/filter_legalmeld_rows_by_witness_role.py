from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows, write_csv
    from phase2.filter_legalmeld_rows_by_use import classify_row, reason_for_row
else:
    from .common import read_csv_rows, write_csv
    from .filter_legalmeld_rows_by_use import classify_row, reason_for_row


DEFAULT_INPUT = Path("data/processed/phase2/legalmeld_validated/legalmeld_metadata_validated.csv")
DEFAULT_OUTPUT_DIR = Path("data/processed/phase2/legalmeld_validated/witness_only_rows")
DEFAULT_BASE_NAME = "witness_rows"
DEFAULT_DISCOVERY_INPUT = Path("data/processed/phase2/paired_hearing_witness_discovery.csv")


def normalize(value: object) -> str:
    return str(value or "").strip()


def is_witness_row(row: dict[str, str]) -> bool:
    return normalize(row.get("speaker_role")).lower() == "witness"


def enrich_row(row: dict[str, str]) -> dict[str, str]:
    categories = classify_row(row)
    if "usable" not in categories and "review" not in categories and "reject" not in categories:
        categories = categories[:]
    row = dict(row)
    row["witness_only"] = "YES"
    row["witness_only_reason"] = "speaker_role=Witness"
    row["training_use_categories"] = ";".join(categories)
    row["training_use_reason"] = reason_for_row(row, categories)
    return row


def split_rows(rows: list[dict[str, str]]) -> tuple[dict[str, list[dict[str, str]]], dict[str, int]]:
    buckets: dict[str, list[dict[str, str]]] = {
        "usable": [],
        "review": [],
        "reject": [],
        "high_confidence": [],
        "medium_confidence": [],
        "low_confidence": [],
    }
    counts: Counter[str] = Counter()
    for row in rows:
        categories = set((row.get("training_use_categories") or "").split(";"))
        for category in buckets:
            if category in categories:
                buckets[category].append(row)
                counts[category] += 1
    return buckets, dict(counts)


def build_hearing_plan(discovery_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_hearing: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in discovery_rows:
        if row.get("contains_actual_witness_testimony") != "YES":
            continue
        hearing_id = normalize(row.get("hearing_id"))
        if not hearing_id:
            continue
        by_hearing[hearing_id].append(row)

    out: list[dict[str, str]] = []
    for hearing_id, rows in by_hearing.items():
        first = rows[0]
        witness_names = sorted({normalize(row.get("witness_name_or_code")) for row in rows if normalize(row.get("witness_name_or_code"))})
        status_counts = Counter(normalize(row.get("witness_identity_status")) for row in rows)
        repeat_counts = Counter(normalize(row.get("is_repeat_witness")) for row in rows)
        out.append(
            {
                "hearing_id": hearing_id,
                "tribunal": normalize(first.get("tribunal")),
                "case_number": normalize(first.get("case_number")),
                "case_family": normalize(first.get("case_family")),
                "hearing_date": normalize(first.get("hearing_date")),
                "witness_name_or_code": " | ".join(witness_names) if witness_names else "UNRESOLVED_WITNESS",
                "witness_identity_status": " | ".join(f"{k}:{v}" for k, v in sorted(status_counts.items()) if k),
                "contains_actual_witness_testimony": "YES",
                "discovery_row_count": str(len(rows)),
                "witness_utterance_count": str(sum(int(normalize(row.get("witness_utterance_count")) or 0) for row in rows)),
                "transcript_speaker_turns": str(sum(int(normalize(row.get("transcript_speaker_turns")) or 0) for row in rows)),
                "question_answer_pair_count": str(sum(int(normalize(row.get("question_answer_pair_count")) or 0) for row in rows)),
                "estimated_testimony_minutes": str(round(sum(float(normalize(row.get("estimated_testimony_minutes")) or 0) for row in rows), 2)),
                "transcript_language": normalize(first.get("transcript_language")),
                "video_language": normalize(first.get("video_language")),
                "is_repeat_witness": "YES" if repeat_counts.get("YES") else "NO",
                "planning_status": "applicable",
                "planning_reason": "discovery_manifest_contains_actual_witness_testimony",
                "notes": f"Grouped from {len(rows)} discovery rows; witness names: {'; '.join(witness_names) if witness_names else 'UNRESOLVED_WITNESS'}",
            }
        )

    out.sort(key=lambda row: (row["tribunal"], row["case_number"], row["hearing_date"], row["hearing_id"]))
    return out


def build_summary(rows: list[dict[str, str]], output_dir: Path, input_path: Path) -> dict[str, object]:
    witness_names = {normalize(row.get("witness_id") or row.get("witness_name") or row.get("witness_name_or_code")) for row in rows if normalize(row.get("witness_id") or row.get("witness_name") or row.get("witness_name_or_code"))}
    hearings = {normalize(row.get("hearing_id")) for row in rows if normalize(row.get("hearing_id"))}
    cases = {normalize(row.get("case_number")) for row in rows if normalize(row.get("case_number"))}
    split_counts = Counter(normalize(row.get("split")) or "unsplit" for row in rows)
    quality_counts = Counter(normalize(row.get("quality_tier")) or "unknown" for row in rows)
    speaker_counts = Counter(normalize(row.get("speaker_role")) or "unknown" for row in rows)
    category_counts = Counter()
    for row in rows:
        for category in (row.get("training_use_categories") or "").split(";"):
            if category:
                category_counts[category] += 1

    return {
        "input_csv": str(input_path),
        "output_dir": str(output_dir),
        "witness_rows": len(rows),
        "distinct_witnesses": len(witness_names),
        "hearings_represented": len(hearings),
        "cases_represented": len(cases),
        "speaker_role_counts": dict(speaker_counts),
        "quality_tier_counts": dict(quality_counts),
        "split_counts": dict(split_counts),
        "category_counts": dict(category_counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter the validated LegalMELD export down to witness rows only, while preserving usable/review/reject buckets."
    )
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT), help="Validated LegalMELD metadata CSV")
    parser.add_argument(
        "--discovery-csv",
        default=str(DEFAULT_DISCOVERY_INPUT),
        help="Optional witness discovery CSV used to create a broader hearing-level planning manifest",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for witness-only outputs")
    parser.add_argument("--base-name", default=DEFAULT_BASE_NAME, help="Prefix for output filenames")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_dir = Path(args.output_dir)
    rows = read_csv_rows(input_path)

    witness_rows = [enrich_row(row) for row in rows if is_witness_row(row)]
    witness_rows.sort(
        key=lambda row: (
            normalize(row.get("hearing_id")),
            normalize(row.get("split")),
            normalize(row.get("utterance_id")),
        )
    )

    buckets, counts = split_rows(witness_rows)
    output_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = list(witness_rows[0].keys()) if witness_rows else list(rows[0].keys()) + [
        "witness_only",
        "witness_only_reason",
        "training_use_categories",
        "training_use_reason",
    ]

    write_csv(output_dir / f"{args.base_name}.csv", witness_rows, fieldnames)
    for category, category_rows in buckets.items():
        write_csv(output_dir / f"{args.base_name}_{category}.csv", category_rows, fieldnames)

    summary = build_summary(witness_rows, output_dir, input_path)
    summary["category_counts"] = {**summary["category_counts"], **counts}

    discovery_path = Path(args.discovery_csv)
    hearing_plan_rows: list[dict[str, str]] = []
    if discovery_path.exists():
        discovery_rows = read_csv_rows(discovery_path)
        hearing_plan_rows = build_hearing_plan(discovery_rows)
        hearing_plan_fields = [
            "hearing_id",
            "tribunal",
            "case_number",
            "case_family",
            "hearing_date",
            "witness_name_or_code",
            "witness_identity_status",
            "contains_actual_witness_testimony",
            "discovery_row_count",
            "witness_utterance_count",
            "transcript_speaker_turns",
            "question_answer_pair_count",
            "estimated_testimony_minutes",
            "transcript_language",
            "video_language",
            "is_repeat_witness",
            "planning_status",
            "planning_reason",
            "notes",
        ]
        write_csv(output_dir / "witness_hearing_plan.csv", hearing_plan_rows, hearing_plan_fields)
        summary.update(
            {
                "hearing_plan_rows": len(hearing_plan_rows),
                "hearing_plan_hearings": len({row["hearing_id"] for row in hearing_plan_rows}),
                "hearing_plan_cases": len({row["case_number"] for row in hearing_plan_rows if row["case_number"]}),
            }
        )

    summary_path = output_dir / f"{args.base_name}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(
        json.dumps(
            {
                "input_csv": str(input_path),
                "discovery_csv": str(discovery_path),
                "output_dir": str(output_dir),
                "summary_json": str(summary_path),
                "hearing_plan_csv": str(output_dir / "witness_hearing_plan.csv") if hearing_plan_rows else "",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
