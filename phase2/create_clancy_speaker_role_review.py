from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a manual review sheet for diarized Clancy speaker clusters")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--examples-per-cluster", type=int, default=3)
    args = parser.parse_args()
    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    required = {"youtube_id", "speaker_cluster_id"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns: {sorted(missing)}")
    rows = []
    for (source, cluster), group in df.groupby(["youtube_id", "speaker_cluster_id"], dropna=False):
        cluster_count = len(group)
        examples = group.head(args.examples_per_cluster)
        rows.append({
            "source_group_id": str(source),
            "speaker_cluster_id": str(cluster),
            "cluster_row_count": str(cluster_count),
            "sample_count": str(len(examples)),
            "sample_utterance_ids": " | ".join(examples.get("utterance_id", examples.index.astype(str)).astype(str)),
            "sample_audio_paths": " | ".join(
                examples.get("clip_audio_path", examples.get("audio_path", pd.Series(dtype=str))).astype(str)
            ),
            "sample_video_paths": " | ".join(
                examples.get("clip_video_path", examples.get("video_path", pd.Series(dtype=str))).astype(str)
            ),
            "sample_text": " || ".join(examples.get("utterance_text", pd.Series(dtype=str)).astype(str)),
            "role_label": "",
            "role_confidence": "",
            "witness_in_segment": "",
            "witness_speaking_status": "",
            "visual_target_role": "",
            "visual_speaker_match": "",
            "review_notes": "",
        })
    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).sort_values(["source_group_id", "speaker_cluster_id"]).to_csv(out, index=False)
    print(f"Wrote {len(rows)} cluster review rows to {out}")


if __name__ == "__main__":
    main()
