from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows, write_csv
else:
    from .common import read_csv_rows, write_csv


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _split(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def _load_covered_source_ids(path: Path) -> set[str]:
    covered: set[str] = set()
    if not path.exists():
        return covered
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for source_id in _split(row.get("source_manifest_source_ids") or row.get("source_id")):
                covered.add(source_id)
    return covered


def _priority_value(row: dict[str, str]) -> int:
    try:
        return int(float(str(row.get("priority") or 0).strip()))
    except Exception:
        return 0


def _tap_docs_value(row: dict[str, str]) -> int:
    try:
        return int(float(str(row.get("tap_docs") or 0).strip()))
    except Exception:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Select the next controlled TAP-bearing tribunal candidate.")
    parser.add_argument(
        "--source-csv",
        default="data/processed/phase2/tap_candidate_manifest.csv",
        help="TAP candidate shortlist to inspect",
    )
    parser.add_argument(
        "--covered-map-csv",
        default="data/phase2/ucr_case_video_strict/inspection/ucr_case_videos_strict_row_source_map.csv",
        help="Strict index row-source map used to exclude already-verified source rows",
    )
    parser.add_argument(
        "--output-csv",
        default="data/processed/phase2/next_tap_verification_manifest.csv",
        help="Output CSV containing the next controlled candidate(s)",
    )
    parser.add_argument(
        "--summary-json",
        default="reports/phase2/next_tap_verification_summary.json",
        help="Output JSON summary for the selection step",
    )
    parser.add_argument("--max-rows", type=int, default=1, help="Maximum number of candidates to keep")
    args = parser.parse_args()

    source_path = Path(args.source_csv)
    covered_map_path = Path(args.covered_map_csv)
    output_path = Path(args.output_csv)
    summary_path = Path(args.summary_json)

    rows = read_csv_rows(source_path)
    covered_source_ids = _load_covered_source_ids(covered_map_path)

    remaining = []
    excluded = 0
    for row in rows:
        source_id = row.get("source_id", "").strip()
        if source_id and source_id in covered_source_ids:
            excluded += 1
            continue
        if _norm(row.get("tap_candidate_status")) not in {"kept", "keep", "selected"}:
            continue
        remaining.append(row)

    remaining.sort(
        key=lambda row: (
            -_priority_value(row),
            -_tap_docs_value(row),
            _norm(row.get("tribunal")),
            _norm(row.get("case_name")),
            _norm(row.get("source_id")),
        )
    )

    selected = remaining[: max(args.max_rows, 0)]
    selected_rows: list[dict[str, str]] = []
    for row in selected:
        row_out = dict(row)
        row_out["selection_reason"] = "next_controlled_tap_candidate"
        row_out["covered_source_id"] = "no" if row.get("source_id", "").strip() not in covered_source_ids else "yes"
        selected_rows.append(row_out)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(selected_rows[0].keys()) if selected_rows else list(rows[0].keys()) + ["selection_reason", "covered_source_id"] if rows else ["selection_reason", "covered_source_id"]
    write_csv(output_path, selected_rows, fieldnames)

    summary = {
        "source_csv": str(source_path),
        "covered_map_csv": str(covered_map_path),
        "total_source_rows": len(rows),
        "covered_source_ids": len(covered_source_ids),
        "excluded_rows": excluded,
        "remaining_rows": len(remaining),
        "selected_rows": len(selected_rows),
        "selected_source_ids": [row.get("source_id", "") for row in selected_rows],
        "selected_case_numbers": [row.get("resolved_case_number", "") for row in selected_rows],
        "selected_case_names": [row.get("case_name", "") for row in selected_rows],
        "notes": (
            "If selected_rows is zero, the current TAP shortlist has already been consumed and the next action is to expand planning manifests again."
        ),
        "output_csv": str(output_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
