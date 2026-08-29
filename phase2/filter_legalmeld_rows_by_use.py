from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import read_csv_rows, write_csv
else:
    from .common import read_csv_rows, write_csv


DEFAULT_INPUT = Path("data/processed/phase2/legalmeld_validated/legalmeld_metadata_validated.csv")
DEFAULT_OUTPUT_DIR = Path("data/processed/phase2/legalmeld_validated/filtered_rows")


def normalize(value: object) -> str:
    return str(value or "").strip()


def norm_upper(value: object) -> str:
    return normalize(value).upper()


def classify_row(row: dict[str, str]) -> list[str]:
    # Turn manifests use clip/role fields rather than LegalMELD alignment tiers.
    if "clip_video_path" in row or "turn_duration_seconds" in row:
        split = normalize(row.get("split"))
        excluded = norm_upper(row.get("corpus_exclusion_status")) == "EXCLUDE"
        role = normalize(row.get("speaker_role")).lower()
        speaking = norm_upper(row.get("witness_speaking_status")) == "SPEAKING"
        clip_status = norm_upper(row.get("clip_status"))
        video_path = normalize(row.get("clip_video_path") or row.get("video_path"))
        audio_path = normalize(row.get("clip_audio_path") or row.get("audio_path"))
        text = normalize(row.get("utterance_text") or row.get("turn_text"))
        try:
            duration = float(row.get("clip_duration_seconds") or row.get("turn_duration_seconds") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        categories: list[str] = []
        valid_media = bool(video_path and audio_path and clip_status not in {"FAILED", "INVALID"})
        valid_candidate = (
            role == "witness"
            and speaking
            and not excluded
            and valid_media
            and bool(text)
            and 0.8 <= duration <= 30.0
            and split in {"train", "dev", "test"}
        )
        if valid_candidate:
            categories.append("usable")
        else:
            categories.append("reject" if excluded or not valid_media or not text else "review")
        if split in {"train", "dev", "test"}:
            categories.append(f"split_{split}")
        return sorted(set(categories))

    split = normalize(row.get("split"))
    quality_tier = norm_upper(row.get("quality_tier"))
    alignment_confidence = norm_upper(row.get("alignment_confidence"))
    manual_review_required = norm_upper(row.get("manual_review_required"))
    alignment_status = norm_upper(row.get("alignment_status"))
    video_quality_status = norm_upper(row.get("video_quality_status"))
    audio_validation_status = norm_upper(row.get("audio_validation_status"))

    categories: list[str] = []

    if split in {"train", "dev", "test"} and quality_tier in {"A", "B"} and manual_review_required != "YES":
        categories.append("usable")

    if manual_review_required == "YES" or split == "review" or quality_tier in {"C", "REJECT"}:
        categories.append("review")

    if quality_tier == "REJECT" or alignment_confidence == "LOW" or alignment_status == "FALLBACK":
        categories.append("reject")

    if alignment_confidence == "HIGH":
        categories.append("high_confidence")
    elif alignment_confidence == "MEDIUM":
        categories.append("medium_confidence")
    elif alignment_confidence == "LOW":
        categories.append("low_confidence")

    if video_quality_status == "VALID":
        categories.append("video_valid")
    if audio_validation_status == "VALID":
        categories.append("audio_valid")
    if split in {"train", "dev", "test"}:
        categories.append(f"split_{split}")

    return sorted(set(categories))


def reason_for_row(row: dict[str, str], categories: list[str]) -> str:
    if "clip_video_path" in row or "turn_duration_seconds" in row:
        excluded = norm_upper(row.get("corpus_exclusion_status")) == "EXCLUDE"
        role = normalize(row.get("speaker_role")) or "UNKNOWN"
        speaking = normalize(row.get("witness_speaking_status")) or "UNKNOWN"
        clip_status = normalize(row.get("clip_status")) or "UNKNOWN"
        duration = normalize(row.get("clip_duration_seconds") or row.get("turn_duration_seconds")) or "0"
        try:
            duration_value = float(duration)
        except ValueError:
            duration_value = 0.0
        if "usable" in categories:
            return f"usable because speaker_role={role}, witness_speaking_status={speaking}, clip_status={clip_status}, duration={duration}s, and source is not excluded"
        reasons = []
        if excluded:
            reasons.append("corpus_exclusion_status=EXCLUDE")
        if role.lower() != "witness":
            reasons.append(f"speaker_role={role}")
        if speaking.upper() != "SPEAKING":
            reasons.append(f"witness_speaking_status={speaking}")
        if clip_status.upper() in {"FAILED", "INVALID"}:
            reasons.append(f"clip_status={clip_status}")
        if not normalize(row.get("utterance_text") or row.get("turn_text")):
            reasons.append("blank transcript text")
        if duration_value < 0.8:
            reasons.append(f"duration={duration}s below 0.8s minimum")
        elif duration_value > 30.0:
            reasons.append(f"duration={duration}s above 30s preferred maximum")
        if "review" in categories:
            return "review because " + ", ".join(reasons or ["candidate needs manual validation"])
        return "reject because " + ", ".join(reasons or ["failed the turn-level witness gate"])

    split = normalize(row.get("split"))
    quality_tier = norm_upper(row.get("quality_tier"))
    alignment_confidence = norm_upper(row.get("alignment_confidence"))
    manual_review_required = norm_upper(row.get("manual_review_required"))
    alignment_status = norm_upper(row.get("alignment_status"))
    text_similarity = normalize(row.get("text_similarity"))
    video_quality_status = norm_upper(row.get("video_quality_status"))
    audio_validation_status = norm_upper(row.get("audio_validation_status"))
    parts: list[str] = []

    if "usable" in categories:
        parts.append(
            f"usable because split={split}, quality_tier={quality_tier}, alignment_confidence={alignment_confidence}, and manual_review_required={manual_review_required}"
        )
    if "review" in categories:
        review_notes = []
        if manual_review_required == "YES":
            review_notes.append("manual review requested")
        if split == "review":
            review_notes.append("already in review split")
        if quality_tier in {"C", "REJECT"}:
            review_notes.append(f"quality_tier={quality_tier}")
        parts.append("review because " + ", ".join(review_notes) if review_notes else "review because the row is not fully trusted")
    if "reject" in categories:
        reject_notes = []
        if quality_tier == "REJECT":
            reject_notes.append("quality_tier=REJECT")
        if alignment_confidence == "LOW":
            reject_notes.append("alignment_confidence=LOW")
        if alignment_status == "FALLBACK":
            reject_notes.append("alignment_status=fallback")
        if text_similarity:
            reject_notes.append(f"text_similarity={text_similarity}")
        parts.append("reject because " + ", ".join(reject_notes) if reject_notes else "reject because the row failed the quality gate")
    if "high_confidence" in categories:
        parts.append("high_confidence because alignment_confidence=HIGH")
    if "medium_confidence" in categories:
        parts.append("medium_confidence because alignment_confidence=MEDIUM")
    if "low_confidence" in categories:
        parts.append("low_confidence because alignment_confidence=LOW")
    if "video_valid" in categories:
        parts.append(f"video_valid because video_quality_status={video_quality_status}")
    if "audio_valid" in categories:
        parts.append(f"audio_valid because audio_validation_status={audio_validation_status}")
    if split in {"train", "dev", "test"}:
        parts.append(f"split_{split} because the row belongs to the {split} partition")

    return " | ".join(parts)


def build_rows(input_rows: list[dict[str, str]]) -> tuple[dict[str, list[dict[str, str]]], dict[str, int]]:
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for row in input_rows:
        categories = classify_row(row)
        row["training_use_categories"] = ";".join(categories)
        row["training_use_reason"] = reason_for_row(row, categories)
        for category in categories:
            buckets[category].append(row)
            counts[category] += 1
    return buckets, dict(counts)


def write_outputs(
    *,
    rows: list[dict[str, str]],
    output_dir: Path,
    base_name: str,
    categories: list[str],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_by_category, counts = build_rows(rows)

    outputs: dict[str, str] = {}
    for category in categories:
        category_rows = rows_by_category.get(category, [])
        out_path = output_dir / f"{base_name}_{category}.csv"
        fieldnames = list(category_rows[0].keys()) if category_rows else list(rows[0].keys()) + ["training_use_categories", "training_use_reason"] if rows else ["training_use_categories", "training_use_reason"]
        write_csv(out_path, category_rows, fieldnames)
        outputs[category] = str(out_path)

    summary_path = output_dir / f"{base_name}_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "input_rows": len(rows),
                "category_counts": counts,
                "output_dir": str(output_dir),
                "base_name": base_name,
                "categories_written": categories,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    outputs["summary_json"] = str(summary_path)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split validated LegalMELD rows into usable, review, reject, and confidence-based categories."
    )
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT), help="Validated LegalMELD metadata CSV")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for category CSV outputs")
    parser.add_argument(
        "--base-name",
        default="legalmeld_rows",
        help="Prefix for output filenames, e.g. legalmeld_rows_usable.csv",
    )
    parser.add_argument(
        "--categories",
        default="usable,review,reject,high_confidence,medium_confidence,low_confidence,video_valid,audio_valid,split_train,split_dev,split_test",
        help="Comma-separated categories to write",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    rows = read_csv_rows(input_path)
    categories = [item.strip() for item in args.categories.split(",") if item.strip()]
    outputs = write_outputs(rows=rows, output_dir=Path(args.output_dir), base_name=args.base_name, categories=categories)

    print(json.dumps({"input_csv": str(input_path), **outputs}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
