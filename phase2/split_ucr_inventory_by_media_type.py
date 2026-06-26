from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir, read_csv_rows, write_csv
else:
    from .common import ensure_dir, read_csv_rows, write_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Split UCR inventory into video and transcript-only manifests")
    parser.add_argument("--inventory-csv", default="data/processed/phase2/ucr_case_inventory.csv", help="Inventory CSV produced by build_ucr_case_inventory.py")
    parser.add_argument("--video-output-csv", default="data/processed/phase2/ucr_video_candidate_manifest.csv", help="Output CSV for video-bearing cases")
    parser.add_argument("--transcript-output-csv", default="data/processed/phase2/ucr_transcript_only_manifest.csv", help="Output CSV for transcript-only cases")
    parser.add_argument("--min-video-docs", type=int, default=1, help="Minimum number of video docs required to keep a case in the video manifest")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.inventory_csv))
    by_case: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("case_number", "").strip(), row.get("case_name", "").strip())
        by_case.setdefault(key, []).append(row)

    video_rows: list[dict[str, object]] = []
    transcript_rows: list[dict[str, object]] = []

    for (case_number, case_name), docs in sorted(by_case.items(), key=lambda item: (item[0][1], item[0][0])):
        video_docs = [d for d in docs if str(d.get("is_video") or "").strip().lower() == "yes"]
        transcript_docs = [d for d in docs if str(d.get("is_video") or "").strip().lower() != "yes"]
        total_docs = len(docs)
        if len(video_docs) >= args.min_video_docs:
            for idx, doc in enumerate(video_docs, start=1):
                video_rows.append(
                    {
                        "case_name": case_name,
                        "case_number": case_number,
                        "document_title": doc.get("document_title", ""),
                        "doc_signature_date": doc.get("doc_signature_date", ""),
                        "document_path": doc.get("document_path", ""),
                        "document_type": doc.get("document_type", ""),
                        "doc_source_desc": doc.get("doc_source_desc", ""),
                        "source_status": doc.get("source_status", ""),
                        "inventory_id": doc.get("inventory_id", ""),
                        "video_rank": idx,
                        "video_docs_in_case": len(video_docs),
                        "total_docs_in_case": total_docs,
                        "notes": "Video-bearing case candidate for tri-modal corpus expansion.",
                    }
                )
        else:
            for doc in transcript_docs:
                transcript_rows.append(
                    {
                        "case_name": case_name,
                        "case_number": case_number,
                        "document_title": doc.get("document_title", ""),
                        "doc_signature_date": doc.get("doc_signature_date", ""),
                        "document_path": doc.get("document_path", ""),
                        "document_type": doc.get("document_type", ""),
                        "doc_source_desc": doc.get("doc_source_desc", ""),
                        "source_status": doc.get("source_status", ""),
                        "inventory_id": doc.get("inventory_id", ""),
                        "notes": "Transcript-only or non-video case candidate.",
                    }
                )

    ensure_dir(Path(args.video_output_csv).parent)
    write_csv(
        Path(args.video_output_csv),
        video_rows,
        [
            "case_name",
            "case_number",
            "document_title",
            "doc_signature_date",
            "document_path",
            "document_type",
            "doc_source_desc",
            "source_status",
            "inventory_id",
            "video_rank",
            "video_docs_in_case",
            "total_docs_in_case",
            "notes",
        ],
    )
    write_csv(
        Path(args.transcript_output_csv),
        transcript_rows,
        [
            "case_name",
            "case_number",
            "document_title",
            "doc_signature_date",
            "document_path",
            "document_type",
            "doc_source_desc",
            "source_status",
            "inventory_id",
            "notes",
        ],
    )
    print(f"Wrote {len(video_rows)} video rows to {args.video_output_csv}")
    print(f"Wrote {len(transcript_rows)} transcript-only rows to {args.transcript_output_csv}")


if __name__ == "__main__":
    main()
