from __future__ import annotations

import argparse
import json
import csv
import hashlib
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _split_list(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    items = []
    for part in text.split("|"):
        part = part.strip()
        if part:
            items.append(part)
    return items


def _load_source_manifest(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({str(k): ("" if v is None else str(v)) for k, v in row.items()})
    return rows


def _match_source_rows(row: dict[str, str], source_rows: list[dict[str, str]]) -> tuple[list[str], list[str], str]:
    case_name = _norm(row.get("case_name"))
    case_number = _norm(row.get("resolved_case_number"))
    title = _norm(row.get("chosen_title"))
    date = _norm(row.get("chosen_date"))

    if not source_rows:
        return [], [], "no source manifest provided"

    matched = []
    relaxed = []
    for src in source_rows:
        src_case_name = _norm(src.get("case_name"))
        src_case_number = _norm(src.get("resolved_case_number"))
        if src_case_name == case_name and src_case_number == case_number:
            relaxed.append(src)
            titles = _norm(src.get("tap_doc_titles"))
            dates = _norm(src.get("tap_doc_dates"))
            if title and title not in titles:
                continue
            if date and date not in dates:
                continue
            matched.append(src)
    if matched:
        return (
            [row.get("source_id", "") for row in matched],
            [row.get("row_number", "") for row in matched],
            "matched by case name, case number, title, and date",
        )
    if relaxed:
        return (
            [row.get("source_id", "") for row in relaxed],
            [row.get("row_number", "") for row in relaxed],
            "matched by case name and case number",
        )
    return [], [], "unmatched"


def _validate_files(paths: list[Path]) -> list[dict[str, object]]:
    if not paths:
        return []
    validator = Path(__file__).resolve().parents[1] / "scripts" / "check_mp4_fallback.py"
    cmd = [sys.executable, str(validator), "--json", *[str(path) for path in paths]]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.stdout.strip():
        payload = json.loads(proc.stdout)
        return list(payload.get("results", []))
    results: list[dict[str, object]] = []
    for path in paths:
        results.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "file_ok": False,
                "file_message": "validator produced no output",
                "ffprobe_ok": False,
                "ffprobe_message": proc.stderr.strip() or "validation failed",
                "status": "FAIL",
            }
        )
    return results


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the strict UCR video index for unique files and source-row lineage")
    parser.add_argument(
        "--index-csv",
        default="data/phase2/ucr_case_video_strict/index/ucr_case_videos_strict.csv",
        help="Strict video index CSV to inspect",
    )
    parser.add_argument(
        "--source-csv",
        default="data/processed/phase2/tap_candidate_manifest.csv",
        help="Original source manifest used to create the strict index",
    )
    parser.add_argument(
        "--output-dir",
        default="data/phase2/ucr_case_video_strict/inspection",
        help="Directory for unique-file and mapping outputs",
    )
    parser.add_argument("--skip-validation", action="store_true", help="Do not run the fallback MP4 validator")
    args = parser.parse_args()

    index_path = Path(args.index_csv)
    source_path = Path(args.source_csv)
    out_dir = ensure_dir(Path(args.output_dir))

    index_rows = read_csv_rows(index_path)
    if not index_rows:
        raise SystemExit(f"No rows found in {index_path}")

    source_rows = _load_source_manifest(source_path) if source_path.exists() else []

    enriched_rows: list[dict[str, object]] = []
    unique_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    recording_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in index_rows:
        local_path = row.get("local_video_path", "").strip()
        resolved_url = row.get("resolved_video_url", "").strip()
        file_key = local_path or resolved_url or row.get("sample_id", "").strip()
        recording_key = resolved_url or file_key
        source_ids, source_row_numbers, source_match_reason = _match_source_rows(row, source_rows)
        row_out = dict(row)
        row_out["file_key"] = file_key
        row_out["recording_key"] = recording_key
        row_out["source_match_reason"] = source_match_reason
        row_out["source_manifest_source_ids"] = " | ".join(source_ids)
        row_out["source_manifest_row_numbers"] = " | ".join(source_row_numbers)
        enriched_rows.append(row_out)
        unique_groups[file_key].append(row_out)
        recording_groups[recording_key].append(row_out)

    mapping_csv = out_dir / "ucr_case_videos_strict_row_source_map.csv"
    unique_csv = out_dir / "ucr_case_videos_strict_unique_files.csv"
    summary_json = out_dir / "ucr_case_videos_strict_inspection_summary.json"

    write_csv(
        mapping_csv,
        enriched_rows,
        [
            "sample_id",
            "record_id",
            "case_name",
            "case_id",
            "resolved_case_number",
            "resolved_video_url",
            "chosen_title",
            "chosen_date",
            "local_video_path",
            "download_status",
            "skip_reason",
            "source_video_url",
            "file_key",
            "recording_key",
            "source_match_reason",
            "source_manifest_source_ids",
            "source_manifest_row_numbers",
        ],
    )

    unique_rows: list[dict[str, object]] = []
    for file_key, rows in sorted(unique_groups.items()):
        first = rows[0]
        statuses = Counter(row.get("download_status", "") for row in rows)
        case_names = sorted({row.get("case_name", "").strip() for row in rows if row.get("case_name", "").strip()})
        case_numbers = sorted({row.get("resolved_case_number", "").strip() for row in rows if row.get("resolved_case_number", "").strip()})
        titles = []
        dates = []
        sample_ids = []
        record_ids = []
        source_ids = []
        for row in rows:
            titles.extend(_split_list(row.get("chosen_title", "")) or ([row.get("chosen_title", "").strip()] if row.get("chosen_title", "").strip() else []))
            dates.extend(_split_list(row.get("chosen_date", "")) or ([row.get("chosen_date", "").strip()] if row.get("chosen_date", "").strip() else []))
            if row.get("sample_id", "").strip():
                sample_ids.append(row["sample_id"].strip())
            if row.get("record_id", "").strip():
                record_ids.append(row["record_id"].strip())
            if row.get("source_manifest_source_ids", "").strip():
                source_ids.extend([item.strip() for item in row["source_manifest_source_ids"].split("|") if item.strip()])
        unique_rows.append(
            {
                "file_key": file_key,
                "local_video_path": first.get("local_video_path", ""),
                "resolved_video_url": first.get("resolved_video_url", ""),
                "row_count": len(rows),
                "unique_case_count": len(case_names),
                "download_status_counts": json.dumps(dict(statuses), sort_keys=True),
                "sample_ids": " | ".join(sorted(set(sample_ids))),
                "record_ids": " | ".join(sorted(set(record_ids))),
                "case_names": " | ".join(case_names),
                "case_numbers": " | ".join(case_numbers),
                "chosen_titles": " | ".join(sorted(set(titles))),
                "chosen_dates": " | ".join(sorted(set(dates))),
                "source_manifest_source_ids": " | ".join(sorted(set(source_ids))),
            }
        )

    write_csv(
        unique_csv,
        unique_rows,
        [
            "file_key",
            "local_video_path",
            "resolved_video_url",
            "row_count",
            "unique_case_count",
            "download_status_counts",
            "sample_ids",
            "record_ids",
            "case_names",
            "case_numbers",
            "chosen_titles",
            "chosen_dates",
            "source_manifest_source_ids",
        ],
    )

    unique_recordings_csv = out_dir / "ucr_case_videos_strict_unique_recordings.csv"
    unique_recording_rows: list[dict[str, object]] = []
    for recording_key, rows in sorted(recording_groups.items()):
        first = rows[0]
        local_paths = sorted({row.get("local_video_path", "").strip() for row in rows if row.get("local_video_path", "").strip()})
        statuses = Counter(row.get("download_status", "") for row in rows)
        case_names = sorted({row.get("case_name", "").strip() for row in rows if row.get("case_name", "").strip()})
        case_numbers = sorted({row.get("resolved_case_number", "").strip() for row in rows if row.get("resolved_case_number", "").strip()})
        titles = sorted({row.get("chosen_title", "").strip() for row in rows if row.get("chosen_title", "").strip()})
        dates = sorted({row.get("chosen_date", "").strip() for row in rows if row.get("chosen_date", "").strip()})
        unique_recording_rows.append(
            {
                "recording_key": recording_key,
                "resolved_video_url": first.get("resolved_video_url", ""),
                "row_count": len(rows),
                "local_video_paths": " | ".join(local_paths),
                "download_status_counts": json.dumps(dict(statuses), sort_keys=True),
                "case_names": " | ".join(case_names),
                "case_numbers": " | ".join(case_numbers),
                "chosen_titles": " | ".join(titles),
                "chosen_dates": " | ".join(dates),
            }
        )

    write_csv(
        unique_recordings_csv,
        unique_recording_rows,
        [
            "recording_key",
            "resolved_video_url",
            "row_count",
            "local_video_paths",
            "download_status_counts",
            "case_names",
            "case_numbers",
            "chosen_titles",
            "chosen_dates",
        ],
    )

    duplicate_file_groups_csv = out_dir / "ucr_case_videos_strict_duplicate_file_groups.csv"
    duplicate_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in unique_rows:
        path = Path(row["local_video_path"])
        if path.exists():
            duplicate_groups[_sha256(path)].append(row)

    duplicate_rows: list[dict[str, object]] = []
    for digest, rows in sorted(duplicate_groups.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(rows) < 2:
            continue
        duplicate_rows.append(
            {
                "sha256": digest,
                "file_count": len(rows),
                "local_video_paths": " | ".join(sorted(r["local_video_path"] for r in rows)),
                "resolved_video_urls": " | ".join(sorted(r["resolved_video_url"] for r in rows)),
                "case_names": " | ".join(sorted({r["case_names"] for r in rows if r["case_names"]})),
                "case_numbers": " | ".join(sorted({r["case_numbers"] for r in rows if r["case_numbers"]})),
            }
        )

    write_csv(
        duplicate_file_groups_csv,
        duplicate_rows,
        [
            "sha256",
            "file_count",
            "local_video_paths",
            "resolved_video_urls",
            "case_names",
            "case_numbers",
        ],
    )

    validation_rows = []
    if not args.skip_validation:
        validation_targets = [Path(row["file_key"]) for row in unique_rows if Path(row["file_key"]).exists()]
        validation_rows = _validate_files(validation_targets)
        validation_csv = out_dir / "ucr_case_videos_strict_validation.csv"
        write_csv(
            validation_csv,
            validation_rows,
            ["path", "exists", "file_ok", "file_message", "ffprobe_ok", "ffprobe_message", "status"],
        )

    summary = {
        "index_rows": len(index_rows),
        "unique_files": len(unique_rows),
        "unique_recordings": len(unique_recording_rows),
        "mapping_rows": len(enriched_rows),
        "source_manifest_rows": len(source_rows),
        "validated_files": len(validation_rows),
        "validation_pass": sum(1 for row in validation_rows if str(row.get("status")) == "PASS"),
        "validation_fail": sum(1 for row in validation_rows if str(row.get("status")) == "FAIL"),
        "output_dir": str(out_dir),
        "mapping_csv": str(mapping_csv),
        "unique_csv": str(unique_csv),
        "unique_recordings_csv": str(unique_recordings_csv),
        "duplicate_file_groups_csv": str(duplicate_file_groups_csv),
        "duplicate_file_groups": len(duplicate_rows),
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Inspected {len(index_rows)} index rows")
    print(f"Wrote row-source map to {mapping_csv}")
    print(f"Wrote unique-file view to {unique_csv}")
    print(f"Wrote unique-recording view to {unique_recordings_csv}")
    if args.skip_validation:
        print("Skipped fallback MP4 validation.")
    else:
        print(f"Wrote validation results for {len(validation_rows)} unique files to {out_dir / 'ucr_case_videos_strict_validation.csv'}")
    print(f"Wrote summary JSON to {summary_json}")


if __name__ == "__main__":
    main()
