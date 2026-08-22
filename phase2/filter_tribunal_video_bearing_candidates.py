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


DEFAULT_SOURCE = Path("data/processed/phase2/tribunal_media_discovery.csv")
DEFAULT_OUTPUT = Path("data/processed/phase2/tribunal_video_bearing_candidates.csv")
DEFAULT_SUMMARY = Path("reports/phase2/tribunal_video_bearing_candidates_summary.json")


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter tribunal media discovery rows to video-bearing candidates.")
    parser.add_argument("--source-csv", default=str(DEFAULT_SOURCE), help="Input tribunal media discovery CSV")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT), help="Filtered video-bearing candidate CSV")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY), help="Summary JSON")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit")
    args = parser.parse_args()

    source_rows = read_csv_rows(Path(args.source_csv))
    if args.limit and args.limit > 0:
        source_rows = source_rows[: args.limit]

    kept_rows = [row for row in source_rows if _norm(row.get("media_status")) == "video_bearing"]
    output_path = Path(args.output_csv)
    write_csv(
        output_path,
        kept_rows,
        [
            "row_number",
            "source_id",
            "tribunal",
            "case_name",
            "candidate_case_numbers",
            "resolved_case_number",
            "case_detail_status",
            "docs_source",
            "total_docs",
            "tap_doc_count",
            "transcript_doc_count",
            "doc_types",
            "tap_doc_titles",
            "tap_doc_dates",
            "transcript_doc_titles",
            "media_status",
            "recommended_action",
            "notes",
        ],
    )

    summary = {
        "source_csv": str(Path(args.source_csv)),
        "output_csv": str(output_path),
        "summary_json": str(Path(args.summary_json)),
        "rows_inspected": len(source_rows),
        "video_bearing_rows": len(kept_rows),
        "case_names": sorted({row.get("case_name", "") for row in kept_rows if row.get("case_name", "")}),
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
