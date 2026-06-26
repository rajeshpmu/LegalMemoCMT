from __future__ import annotations

import argparse
from pathlib import Path

from .common import ensure_dir, read_csv_rows, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 2 text-only manifest from downloaded Supreme Court transcripts")
    parser.add_argument("--input-csv", default="data/phase2/scotus/index/scotus_transcripts.csv", help="Downloaded SCOTUS transcript index CSV")
    parser.add_argument("--output-csv", default="data/processed/phase2/scotus_text_manifest.csv", help="Output text-only manifest CSV")
    parser.add_argument("--split", default="unsplit", help="Split label to assign to all rows")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.input_csv))
    out_rows: list[dict[str, object]] = []

    for idx, row in enumerate(rows, start=1):
        sample_id = row.get("sample_id") or f"scotus_{idx}"
        transcript = (row.get("transcript") or "").strip()
        text_path = (row.get("text_path") or "").strip()
        source_url = (row.get("source_url") or "").strip()
        title = (row.get("title") or "").strip()

        out_rows.append(
            {
                "sample_id": sample_id,
                "split": args.split,
                "court": "US_Supreme_Court",
                "case_name": title,
                "source_url": source_url,
                "text_path": text_path,
                "text": transcript,
                "audio_path": "",
                "video_path": "",
                "label": "",
                "notes": "Text-only legal adaptation corpus from public Supreme Court oral argument transcripts.",
            }
        )

    ensure_dir(Path(args.output_csv).parent)
    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "sample_id",
            "split",
            "court",
            "case_name",
            "source_url",
            "text_path",
            "text",
            "audio_path",
            "video_path",
            "label",
            "notes",
        ],
    )
    print(f"Wrote {len(out_rows)} SCOTUS text rows to {args.output_csv}")


if __name__ == "__main__":
    main()
