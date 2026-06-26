from __future__ import annotations

import argparse
import re
from pathlib import Path

from .common import ensure_dir, read_csv_rows, write_csv


def _slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return text or "item"


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand Phase 2 planning manifests into download targets")
    parser.add_argument("--tribunal-sources", default="data/phase2/source_manifests/tribunal_sources_target_dataset.csv", help="Tribunal planning manifest")
    parser.add_argument("--witness-manifest", default="data/phase2/source_manifests/witness_harvest_manifest.csv", help="Witness planning manifest")
    parser.add_argument("--output-csv", default="data/processed/phase2/phase2_expanded_planning_manifest.csv", help="Expanded output CSV")
    parser.add_argument("--mode", choices=["witness", "tribunal", "both"], default="both", help="Which manifest(s) to expand")
    args = parser.parse_args()

    out_rows: list[dict[str, object]] = []
    if args.mode in {"tribunal", "both"}:
        tribunal_rows = read_csv_rows(Path(args.tribunal_sources))
        for idx, row in enumerate(tribunal_rows, start=1):
            subset_id = (row.get("subset_id") or f"tribunal_{idx}").strip()
            case_family = (row.get("case_family") or "").strip()
            tribunal = (row.get("tribunal") or "").strip()
            out_rows.append(
                {
                    "manifest_kind": "tribunal",
                    "source_id": subset_id,
                    "tribunal": tribunal,
                    "case_name": case_family,
                    "witness_name": "",
                    "witness_type": "",
                    "source_url": row.get("source_url", ""),
                    "video_url": "",
                    "transcript_url": "",
                    "priority": row.get("target_witnesses", ""),
                    "notes": row.get("notes", ""),
                    "download_scope": "case_inventory",
                }
            )

    if args.mode in {"witness", "both"}:
        witness_rows = read_csv_rows(Path(args.witness_manifest))
        for idx, row in enumerate(witness_rows, start=1):
            case_name = (row.get("case_name") or "").strip()
            tribunal = (row.get("tribunal") or "").strip()
            witness_name = (row.get("witness_name") or row.get("witness_name_or_code") or f"witness_{idx}").strip()
            source_id = f"{_slug(tribunal)}_{_slug(case_name)}_{_slug(witness_name)}_{idx}"
            out_rows.append(
                {
                    "manifest_kind": "witness",
                    "source_id": source_id,
                    "tribunal": tribunal,
                    "case_name": case_name,
                    "witness_name": witness_name,
                    "witness_type": (row.get("witness_type") or "").strip(),
                    "source_url": "",
                    "video_url": (row.get("video_url") or "").strip(),
                    "transcript_url": (row.get("transcript_url") or "").strip(),
                    "priority": row.get("annotation_status", ""),
                    "notes": row.get("notes", ""),
                    "download_scope": "witness",
                }
            )

    ensure_dir(Path(args.output_csv).parent)
    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "manifest_kind",
            "source_id",
            "tribunal",
            "case_name",
            "witness_name",
            "witness_type",
            "source_url",
            "video_url",
            "transcript_url",
            "priority",
            "notes",
            "download_scope",
        ],
    )
    print(f"Wrote {len(out_rows)} expanded planning rows to {args.output_csv}")


if __name__ == "__main__":
    main()
