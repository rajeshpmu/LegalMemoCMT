from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


def quantile(values: list[float], fraction: float) -> float:
    index = (len(values) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return values[low]
    return values[low] + (values[high] - values[low]) * (index - low)


def duration(row: dict[str, str]) -> float:
    try:
        return float(row.get("clip_duration_seconds") or 0.0)
    except ValueError:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Clancy turn-duration outlier report")
    parser.add_argument("--input-csv", default="data/processed/phase2/clancy/clancy_turn_manifest_post_rejection.csv")
    parser.add_argument("--output-csv", default="data/processed/phase2/clancy/clancy_duration_outliers.csv")
    parser.add_argument("--summary-json", default="reports/phase2/clancy_duration_outlier_summary.json")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    with input_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    values = sorted(duration(row) for row in rows)
    if not values:
        raise SystemExit(f"No rows found in {input_path}")

    q1 = quantile(values, 0.25)
    q3 = quantile(values, 0.75)
    iqr = q3 - q1
    upper_fence = q3 + 1.5 * iqr
    extreme_fence = q3 + 3.0 * iqr

    outliers = []
    for row in rows:
        seconds = duration(row)
        if seconds <= upper_fence:
            continue
        if seconds > 300:
            band = "EXTREME_OVER_300_SECONDS"
            action = "URGENT_MANUAL_INSPECTION; split if valid testimony or reject if break/non-testimony"
        elif seconds > 60:
            band = "HIGH_OVER_60_SECONDS"
            action = "MANUAL_INSPECTION; split at pauses/sentences/speaker boundaries before training"
        elif seconds > 30:
            band = "REVIEW_OVER_30_SECONDS"
            action = "REVIEW; retain only if one coherent turn, otherwise split"
        else:
            band = "IQR_OUTLIER_OVER_20_8155_SECONDS"
            action = "SAMPLE_REVIEW; check boundary quality and transcript completeness"
        out = {
            "turn_id": row.get("turn_id", ""),
            "youtube_id": row.get("youtube_id", ""),
            "source_url": row.get("source_url", ""),
            "title": row.get("title", ""),
            "raw_video_path": row.get("source_video_path", ""),
            "raw_subtitle_path": row.get("subtitle_path", ""),
            "clip_video_path": row.get("clip_video_path", ""),
            "clip_audio_path": row.get("clip_audio_path", ""),
            "turn_start_time": row.get("turn_start_time", ""),
            "turn_end_time": row.get("turn_end_time", ""),
            "clip_duration_seconds": f"{seconds:.3f}",
            "turn_source_utterance_count": row.get("turn_source_utterance_count", ""),
            "turn_text_preview": (row.get("turn_text") or row.get("utterance_text") or "")[:240],
            "outlier_band": band,
            "recommended_action": action,
        }
        outliers.append(out)

    outliers.sort(key=lambda row: float(row["clip_duration_seconds"]), reverse=True)
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(outliers[0].keys()) if outliers else [
        "turn_id", "youtube_id", "source_url", "title", "raw_video_path", "raw_subtitle_path",
        "clip_video_path", "clip_audio_path", "turn_start_time", "turn_end_time",
        "clip_duration_seconds", "turn_source_utterance_count", "turn_text_preview",
        "outlier_band", "recommended_action",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(outliers)

    summary = {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "total_rows": len(rows),
        "q1_seconds": round(q1, 3),
        "q3_seconds": round(q3, 3),
        "iqr_seconds": round(iqr, 3),
        "upper_iqr_fence_seconds": round(upper_fence, 3),
        "extreme_iqr_fence_seconds": round(extreme_fence, 3),
        "outlier_rows": len(outliers),
        "outlier_band_counts": dict(Counter(row["outlier_band"] for row in outliers)),
        "rows_over_30_seconds": sum(duration(row) > 30 for row in rows),
        "rows_over_60_seconds": sum(duration(row) > 60 for row in rows),
        "rows_over_300_seconds": sum(duration(row) > 300 for row in rows),
        "interpretation": "IQR outliers are review candidates. Do not automatically reject every statistical outlier; split valid testimony and reject only confirmed non-value or unresolvable records.",
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
