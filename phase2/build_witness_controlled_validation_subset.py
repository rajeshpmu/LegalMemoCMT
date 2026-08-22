from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows, write_csv
else:
    from .common import read_csv_rows, write_csv


DEFAULT_WITNESS_ROWS = Path("data/processed/phase2/legalmeld_validated/witness_only_rows/witness_rows.csv")
DEFAULT_HEARING_PLAN = Path("data/processed/phase2/legalmeld_validated/witness_only_rows/witness_hearing_plan.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/legalmeld_validated/witness_only_rows/witness_controlled_validation_subset.csv")
DEFAULT_SUMMARY = Path("reports/phase2/witness_controlled_validation_subset_summary.json")
DEFAULT_MAX_HEARINGS = 10

EXAM_HINTS = (
    "examination-in-chief",
    "cross-examination",
    "re-examination",
    "re-direct",
    "recross",
    "questioning by the judges",
    "court questioning",
)


def normalize(value: object) -> str:
    return str(value or "").strip()


def clean_witness_label(value: object) -> str:
    text = normalize(value)
    if not text:
        return ""
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if parts:
        first = parts[0]
        if any(hint in first.lower() for hint in EXAM_HINTS):
            return ""
        return first
    return text


def build_witness_key(row: dict[str, str]) -> str:
    label = clean_witness_label(row.get("witness_name_or_code"))
    if label:
        return label
    label = normalize(row.get("witness_name_or_code"))
    return label


def score_hearing(row: dict[str, str]) -> float:
    discovery = float(normalize(row.get("discovery_row_count")) or 0)
    minutes = float(normalize(row.get("estimated_testimony_minutes")) or 0)
    status = normalize(row.get("witness_identity_status")).upper()
    score = minutes + discovery * 25.0
    if "PROTECTED_CODE" in status and "PUBLIC_NAME" in status:
        score += 20.0
    elif "PROTECTED_CODE" in status:
        score += 15.0
    elif "PUBLIC_NAME" in status:
        score += 10.0
    if discovery > 1:
        score += 5.0
    if minutes <= 0:
        score -= 20.0
    return round(score, 2)


def load_anchor_hearings(path: Path) -> set[str]:
    return {normalize(row.get("hearing_id")) for row in read_csv_rows(path) if normalize(row.get("hearing_id"))}


def build_subset(hearing_plan_csv: Path, anchor_hearings: set[str], max_hearings: int) -> list[dict[str, str]]:
    rows = read_csv_rows(hearing_plan_csv)
    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()

    for row in rows:
        hearing_id = normalize(row.get("hearing_id"))
        if hearing_id in anchor_hearings:
            selected.append(
                {
                    **row,
                    "witness_name_or_code_clean": build_witness_key(row),
                    "validation_track": "anchor",
                    "validation_reason": "already validated in the utterance-level witness subset",
                    "controlled_validation_score": f"{score_hearing(row):.2f}",
                    "manual_note": "kept as an anchor hearing with validated witness utterance rows",
                }
            )
            selected_ids.add(hearing_id)

    ranked: list[tuple[float, dict[str, str]]] = []
    for row in rows:
        hearing_id = normalize(row.get("hearing_id"))
        if not hearing_id or hearing_id in selected_ids:
            continue
        ranked.append((score_hearing(row), row))
    ranked.sort(key=lambda item: (-item[0], normalize(item[1].get("hearing_date")), normalize(item[1].get("hearing_id"))))

    for score, row in ranked:
        if len(selected) >= max_hearings:
            break
        selected.append(
            {
                **row,
                "witness_name_or_code_clean": build_witness_key(row),
                "validation_track": "promoted",
                "validation_reason": "manually promoted from the broader hearing discovery plan for controlled validation",
                "controlled_validation_score": f"{score:.2f}",
                "manual_note": "selected because it has a strong discovery signal, a traceable witness identity, and useful testimony coverage",
            }
        )

    selected.sort(
        key=lambda row: (
            0 if row.get("validation_track") == "anchor" else 1,
            normalize(row.get("hearing_date")),
            normalize(row.get("hearing_id")),
        )
    )
    return selected


def build_summary(rows: list[dict[str, str]], anchor_hearings: set[str]) -> dict[str, object]:
    hearing_ids = [normalize(row.get("hearing_id")) for row in rows if normalize(row.get("hearing_id"))]
    estimated_minutes = sum(float(normalize(row.get("estimated_testimony_minutes")) or 0) for row in rows)
    witness_names = sorted({normalize(row.get("witness_name_or_code")) for row in rows if normalize(row.get("witness_name_or_code"))})
    cases = sorted({(normalize(row.get("tribunal")), normalize(row.get("case_number")), normalize(row.get("case_family"))) for row in rows})
    return {
        "selected_hearings": len(set(hearing_ids)),
        "selected_rows": len(rows),
        "anchor_hearings": len(anchor_hearings),
        "promoted_hearings": len(set(hearing_ids) - anchor_hearings),
        "cases_represented": len(cases),
        "estimated_testimony_minutes": round(estimated_minutes, 2),
        "distinct_witness_labels": len(witness_names),
        "witness_labels": witness_names,
        "selected_hearing_ids": sorted(set(hearing_ids)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a controlled validation subset from the broader witness hearing plan.")
    parser.add_argument("--witness-rows-csv", default=str(DEFAULT_WITNESS_ROWS))
    parser.add_argument("--hearing-plan-csv", default=str(DEFAULT_HEARING_PLAN))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--max-hearings", type=int, default=DEFAULT_MAX_HEARINGS)
    args = parser.parse_args()

    anchor_hearings = load_anchor_hearings(Path(args.witness_rows_csv))
    selected_rows = build_subset(Path(args.hearing_plan_csv), anchor_hearings, args.max_hearings)

    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(selected_rows[0].keys()) if selected_rows else []
    write_csv(output_path, selected_rows, fieldnames)

    summary = build_summary(selected_rows, anchor_hearings)
    summary.update(
        {
            "witness_rows_csv": str(Path(args.witness_rows_csv)),
            "hearing_plan_csv": str(Path(args.hearing_plan_csv)),
            "output_csv": str(output_path),
            "max_hearings": args.max_hearings,
            "manual_note": "The promoted rows were selected from the broader hearing discovery plan as a controlled validation pass; this is a planning subset, not final corpus expansion.",
        }
    )
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(
        json.dumps(
            {
                "output_csv": str(output_path),
                "summary_json": str(summary_path),
                "selected_hearings": summary["selected_hearing_ids"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
