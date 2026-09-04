"""Prepare and finalize the Tupac visible-witness-speaking review manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


VISUAL_COLUMNS = {
    "visual_speaker_match": "",
    "speaker_visible_during_speech": "",
    "face_visible_ratio": "",
    "visual_verification_status": "UNREVIEWED",
    "visual_verification_confidence": "",
    "visual_reviewer": "",
    "visual_review_notes": "",
}
VALID_YES_NO = {"YES", "NO", "UNKNOWN", ""}
VALID_STATUS = {"HUMAN_VERIFIED", "NOT_VERIFIED", "UNREVIEWED", ""}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Prepare or finalize Tupac visible-witness-speaking annotations."
    )
    p.add_argument("--mode", choices={"prepare", "finalize"}, required=True)
    p.add_argument("--input-csv", required=True, help="Validated Tupac witness-speaking CSV")
    p.add_argument("--output-csv", required=True)
    p.add_argument("--summary-json", required=True)
    p.add_argument("--rejections-csv", default="")
    p.add_argument("--reviewer", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--require-asd", action="store_true", help="Require ASD pass fields during finalize")
    p.add_argument("--asd-confidence-threshold", type=float, default=0.70)
    p.add_argument("--asd-frame-ratio-threshold", type=float, default=0.60)
    return p


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Input CSV does not exist: {path}")
    return pd.read_csv(path, dtype=str).fillna("")


def write_summary(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


def prepare(df: pd.DataFrame, args: argparse.Namespace) -> dict:
    required = {"utterance_id", "speaker_role", "witness_speaking_status"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Input manifest missing columns: {missing}")

    for column, default in VISUAL_COLUMNS.items():
        if column not in df.columns:
            df[column] = default
    if args.reviewer:
        df["visual_reviewer"] = args.reviewer
    if args.notes:
        df["visual_review_notes"] = args.notes

    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return {
        "mode": "prepare",
        "input_csv": str(args.input_csv),
        "output_csv": str(out),
        "rows_written": int(len(df)),
        "visual_fields_initialized": list(VISUAL_COLUMNS),
        "instructions": [
            "Review each video clip, not only the transcript or face embedding.",
            "Set visual_speaker_match=YES only when the visible person is the diarized witness.",
            "Set speaker_visible_during_speech=YES only when that person is visibly speaking during the utterance.",
            "Set visual_verification_status=HUMAN_VERIFIED after manual inspection.",
            "Use face_visible_ratio as an approximate 0-1 reviewer estimate, not a model probability.",
        ],
    }


def finalize(df: pd.DataFrame, args: argparse.Namespace) -> dict:
    required = {
        "utterance_id",
        "visual_speaker_match",
        "speaker_visible_during_speech",
        "visual_verification_status",
    }
    if args.require_asd:
        required.update({"active_speaker_detected", "active_speaker_confidence", "active_speaker_frame_ratio"})
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Review CSV missing columns: {missing}")

    for column in ("visual_speaker_match", "speaker_visible_during_speech"):
        bad = sorted(set(df[column].str.upper()) - VALID_YES_NO)
        if bad:
            raise SystemExit(f"Invalid {column} values: {bad}")
    bad_status = sorted(set(df["visual_verification_status"].str.upper()) - VALID_STATUS)
    if bad_status:
        raise SystemExit(f"Invalid visual_verification_status values: {bad_status}")

    ratio = pd.to_numeric(df.get("face_visible_ratio", ""), errors="coerce")
    invalid_ratio = ratio.notna() & ~ratio.between(0.0, 1.0)
    if invalid_ratio.any():
        raise SystemExit("face_visible_ratio must be blank or between 0 and 1")

    yes_match = df["visual_speaker_match"].str.upper().eq("YES")
    yes_visible = df["speaker_visible_during_speech"].str.upper().eq("YES")
    verified = df["visual_verification_status"].str.upper().eq("HUMAN_VERIFIED")
    visual_gate = yes_match & yes_visible & verified
    asd_gate = pd.Series(True, index=df.index)
    if args.require_asd:
        asd_conf = pd.to_numeric(df.get("active_speaker_confidence", ""), errors="coerce")
        asd_ratio = pd.to_numeric(df.get("active_speaker_frame_ratio", ""), errors="coerce")
        asd_detected = df["active_speaker_detected"].astype(str).str.upper().eq("YES")
        asd_gate = (
            asd_detected
            & asd_conf.ge(args.asd_confidence_threshold)
            & asd_ratio.ge(args.asd_frame_ratio_threshold)
        )
    selected = df.loc[visual_gate & asd_gate].copy()
    rejected = df.loc[~(visual_gate & asd_gate)].copy()

    selected["tupac_visible_witness_speaking"] = "YES"
    selected["visual_corpus_status"] = "HUMAN_VERIFIED"
    rejected["tupac_visible_witness_speaking"] = "NO"
    rejected["visual_corpus_rejection_reason"] = "visual_gate_not_satisfied"

    out = Path(args.output_csv)
    reject_out = Path(args.rejections_csv or str(out.with_name(out.stem + "_rejections.csv")))
    out.parent.mkdir(parents=True, exist_ok=True)
    reject_out.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(out, index=False)
    rejected.to_csv(reject_out, index=False)

    return {
        "mode": "finalize",
        "input_csv": str(args.input_csv),
        "output_csv": str(out),
        "rejections_csv": str(reject_out),
        "rows_input": int(len(df)),
        "rows_verified_visible_witness_speaking": int(len(selected)),
        "rows_rejected_or_pending": int(len(rejected)),
        "verification_rule": "visual_speaker_match=YES AND speaker_visible_during_speech=YES AND visual_verification_status=HUMAN_VERIFIED",
        "require_asd": bool(args.require_asd),
        "asd_rule": "active_speaker_detected=YES AND active_speaker_confidence>=threshold AND active_speaker_frame_ratio>=threshold" if args.require_asd else "not required",
        "notes": [
            "This is a human visual verification gate, not automatic active-speaker detection.",
            "Face embeddings alone do not prove that the visible face is speaking.",
            "Rejected and pending rows are preserved in the rejections CSV.",
            "Only verified rows should be called the visible-witness-speaking corpus.",
        ],
    }


def main() -> None:
    args = parser().parse_args()
    source = Path(args.input_csv)
    df = load_csv(source)
    summary = prepare(df, args) if args.mode == "prepare" else finalize(df, args)
    write_summary(Path(args.summary_json), summary)


if __name__ == "__main__":
    main()
