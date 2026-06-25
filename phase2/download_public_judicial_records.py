from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

from .common import download_file, ensure_dir, extract_text_from_file, read_csv_rows, safe_filename, sha1_short, slugify, write_csv


TEMPLATE_COLUMNS = [
    "record_id",
    "case_id",
    "court",
    "source_type",
    "language",
    "url",
    "audio_url",
    "video_url",
    "split_hint",
    "notes",
]


def write_template(path: Path) -> None:
    ensure_dir(path.parent)
    rows = [
        {
            "record_id": "example_record_001",
            "case_id": "example_case_001",
            "court": "IRMCT",
            "source_type": "judicial_record",
            "language": "en",
            "url": "",
            "audio_url": "",
            "video_url": "",
            "split_hint": "unsplit",
            "notes": "Fill this row with a public archive URL exported from the archive search or your own curated source list.",
        }
    ]
    write_csv(path, rows, TEMPLATE_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download public tribunal and judicial records from a source list")
    parser.add_argument("--source-csv", type=str, default="", help="CSV containing archive URLs and metadata")
    parser.add_argument("--output-root", type=str, default="data/phase2/tribunal_records", help="Download root directory")
    parser.add_argument("--index-csv", type=str, default="", help="Optional path for the output index CSV")
    parser.add_argument("--write-template", action="store_true", help="Write a template source CSV and exit")
    parser.add_argument("--template-path", type=str, default="data/phase2/tribunal_sources_template.csv", help="Template CSV path")
    args = parser.parse_args()

    if args.write_template:
        write_template(Path(args.template_path))
        print(f"Wrote template source list to {args.template_path}")
        return

    if not args.source_csv:
        raise SystemExit("--source-csv is required unless --write-template is used")

    source_rows = read_csv_rows(Path(args.source_csv))
    out = Path(args.output_root)
    raw_dir = ensure_dir(out / "raw")
    text_dir = ensure_dir(out / "text")
    index_dir = ensure_dir(out / "index")
    index_csv = Path(args.index_csv) if args.index_csv else index_dir / "tribunal_records.csv"

    rows: list[dict[str, object]] = []
    for idx, src in enumerate(source_rows, start=1):
        record_id = (src.get("record_id") or src.get("sample_id") or f"record_{idx}").strip()
        record_slug = slugify(record_id)
        case_id = (src.get("case_id") or record_id).strip()
        court = (src.get("court") or "tribunal").strip()
        source_type = (src.get("source_type") or "judicial_record").strip()
        language = (src.get("language") or "en").strip()
        url = (src.get("url") or src.get("source_url") or "").strip()
        audio_url = (src.get("audio_url") or "").strip()
        video_url = (src.get("video_url") or "").strip()
        split_hint = (src.get("split_hint") or "unsplit").strip()
        notes = (src.get("notes") or "").strip()

        transcript = (src.get("transcript") or src.get("text") or "").strip()
        raw_path = ""
        transcript_path = ""
        audio_path = ""
        video_path = ""

        if url:
            fallback = safe_filename(url, f"{record_id}.bin")
            record_dir = ensure_dir(raw_dir / slugify(court) / record_slug)
            raw_path_obj = record_dir / fallback
            try:
                if not raw_path_obj.exists():
                    download_file(url, raw_path_obj)
                raw_path = str(raw_path_obj)
                if not transcript:
                    transcript = extract_text_from_file(raw_path_obj)
            except Exception as exc:
                print(f"Skipped main URL for {record_id}: {exc}")

        if audio_url:
            audio_name = safe_filename(audio_url, f"{record_id}_audio.bin")
            audio_path_obj = ensure_dir(raw_dir / slugify(court) / record_id / "audio") / audio_name
            try:
                if not audio_path_obj.exists():
                    download_file(audio_url, audio_path_obj)
                audio_path = str(audio_path_obj)
            except Exception as exc:
                print(f"Skipped audio URL for {record_id}: {exc}")

        if video_url:
            video_name = safe_filename(video_url, f"{record_id}_video.bin")
            video_path_obj = ensure_dir(raw_dir / slugify(court) / record_id / "video") / video_name
            try:
                if not video_path_obj.exists():
                    download_file(video_url, video_path_obj)
                video_path = str(video_path_obj)
            except Exception as exc:
                print(f"Skipped video URL for {record_id}: {exc}")

        if transcript:
            transcript_path_obj = text_dir / f"{record_slug}.txt"
            transcript_path_obj.write_text(transcript, encoding="utf-8")
            transcript_path = str(transcript_path_obj)

        rows.append(
            {
                "sample_id": f"{slugify(court)}_{record_slug}_{sha1_short(url or record_id)}",
                "case_id": case_id,
                "court": court,
                "source_type": source_type,
                "language": language,
                "split_hint": split_hint,
                "source_url": url,
                "record_id": record_id,
                "raw_path": raw_path,
                "transcript_path": transcript_path,
                "transcript": transcript,
                "audio_path": audio_path,
                "video_path": video_path,
                "notes": notes,
            }
        )

    write_csv(
        index_csv,
        rows,
        [
            "sample_id",
            "case_id",
            "court",
            "source_type",
            "language",
            "split_hint",
            "source_url",
            "record_id",
            "raw_path",
            "transcript_path",
            "transcript",
            "audio_path",
            "video_path",
            "notes",
        ],
    )
    print(f"Wrote {len(rows)} tribunal record rows to {index_csv}")


if __name__ == "__main__":
    main()
