"""Classify ASD outputs into automated candidates, manual review, and rejects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def yes(value: object) -> bool:
    return str(value or "").strip().upper() == "YES"


def number(value: object) -> float:
    result = pd.to_numeric(value, errors="coerce")
    return float(result) if pd.notna(result) else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--tracks-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--auto-csv", default="")
    parser.add_argument("--manual-csv", default="")
    parser.add_argument("--reject-csv", default="")
    parser.add_argument("--confidence-threshold", type=float, default=0.80)
    parser.add_argument("--frame-ratio-threshold", type=float, default=0.75)
    parser.add_argument("--min-track-frames", type=int, default=3)
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    tracks = pd.read_csv(args.tracks_csv, dtype=str).fillna("")
    required = {"utterance_id", "speaker_role", "witness_speaking_status", "active_speaker_detected", "active_speaker_confidence", "active_speaker_frame_ratio"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"ASD manifest missing columns: {missing}")
    if "utterance_id" not in tracks.columns or "face_track_id" not in tracks.columns:
        raise SystemExit("Tracks CSV must contain utterance_id and face_track_id")

    track_stats = (
        tracks[tracks["face_track_id"].astype(str).str.strip().ne("")]
        .groupby("utterance_id")["face_track_id"]
        .agg(track_count="nunique", max_track_frames="size")
        .reset_index()
    )
    df = df.merge(track_stats, on="utterance_id", how="left")
    df["track_count"] = pd.to_numeric(df["track_count"], errors="coerce").fillna(0).astype(int)
    df["max_track_frames"] = pd.to_numeric(df["max_track_frames"], errors="coerce").fillna(0).astype(int)

    statuses, reasons, priorities = [], [], []
    for _, row in df.iterrows():
        role_ok = str(row.get("speaker_role", "")).strip().lower() == "witness"
        speaking_ok = str(row.get("witness_speaking_status", "")).strip().upper() == "SPEAKING"
        excluded = str(row.get("corpus_exclusion_status", "")).strip().upper() == "EXCLUDE"
        face_ok = yes(row.get("face_detected")) and row["track_count"] == 1 and row["max_track_frames"] >= args.min_track_frames
        asd_yes = yes(row.get("active_speaker_detected"))
        confidence = number(row.get("active_speaker_confidence"))
        ratio = number(row.get("active_speaker_frame_ratio"))
        strong_asd = asd_yes and confidence >= args.confidence_threshold and ratio >= args.frame_ratio_threshold
        if excluded or not role_ok or not speaking_ok or not yes(row.get("face_detected")):
            status, reason, priority = "AUTO_REJECT_CANDIDATE", "excluded_or_not_verified_witness_speaking_input", "LOW"
        elif not face_ok:
            status, reason, priority = "MANUAL_REVIEW_REQUIRED", "multiple_or_unstable_face_tracks", "HIGH"
        elif not strong_asd:
            status, reason, priority = "MANUAL_REVIEW_REQUIRED", "weak_or_negative_asd_evidence", "HIGH"
        else:
            status, reason, priority = "AUTO_ACCEPT_CANDIDATE", "one_stable_face_track_with_strong_asd_screen", "MEDIUM"
        statuses.append(status)
        reasons.append(reason)
        priorities.append(priority)

    df["asd_review_status"] = statuses
    df["asd_review_reason"] = reasons
    df["asd_review_priority"] = priorities
    df["asd_identity_warning"] = "Speaker-face identity still requires human confirmation"
    df["visual_emotion_eligible"] = df.apply(
        lambda row: "YES"
        if row["asd_review_status"] == "AUTO_ACCEPT_CANDIDATE"
        and yes(row.get("speaker_face_match"))
        and yes(row.get("target_witness_visible"))
        and yes(row.get("visual_speaker_match"))
        and yes(row.get("speaker_visible_during_speech"))
        and str(row.get("visual_verification_status", "")).upper() == "HUMAN_VERIFIED"
        else "NO",
        axis=1,
    )

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    paths = {
        "auto": Path(args.auto_csv) if args.auto_csv else output.with_name(output.stem + "_auto_candidates.csv"),
        "manual": Path(args.manual_csv) if args.manual_csv else output.with_name(output.stem + "_manual_review.csv"),
        "reject": Path(args.reject_csv) if args.reject_csv else output.with_name(output.stem + "_reject_candidates.csv"),
    }
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        selected = {
            "auto": "AUTO_ACCEPT_CANDIDATE",
            "manual": "MANUAL_REVIEW_REQUIRED",
            "reject": "AUTO_REJECT_CANDIDATE",
        }[key]
        df[df["asd_review_status"] == selected].to_csv(path, index=False)

    summary = {
        "input_csv": str(args.input_csv),
        "tracks_csv": str(args.tracks_csv),
        "output_csv": str(output),
        "rows_processed": int(len(df)),
        "status_counts": df["asd_review_status"].value_counts().to_dict(),
        "priority_counts": df["asd_review_priority"].value_counts().to_dict(),
        "auto_candidates_csv": str(paths["auto"]),
        "manual_review_csv": str(paths["manual"]),
        "reject_candidates_csv": str(paths["reject"]),
        "thresholds": {
            "active_speaker_confidence": args.confidence_threshold,
            "active_speaker_frame_ratio": args.frame_ratio_threshold,
            "minimum_track_frames": args.min_track_frames,
        },
        "notes": [
            "AUTO_ACCEPT_CANDIDATE is a screening result, not an accepted visible-witness label.",
            "A single face track does not prove that the face belongs to the witness; speaker-face identity remains a human gate.",
            "visual_emotion_eligible becomes YES only when explicit human visual fields also pass.",
            "Review thresholds are starting points and require validation against a stratified sample.",
        ],
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
