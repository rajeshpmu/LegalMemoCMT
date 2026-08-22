from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


VALID_ROLES = {"Witness", "Prosecutor", "Defence", "Judge", "Other", "UNKNOWN"}
VALID_STATUS = {"SPEAKING", "LISTENING_OR_ADDRESSED", "UNKNOWN"}
VALID_WITNESS_PRESENCE = {"YES", "NO", "UNKNOWN"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply manually verified Clancy speaker roles to a manifest")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--role-map-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()
    manifest = pd.read_csv(args.input_csv, dtype=str).fillna("")
    role_map = pd.read_csv(args.role_map_csv, dtype=str).fillna("")
    required = {"source_group_id", "speaker_cluster_id", "role_label", "role_confidence"}
    missing = required - set(role_map.columns)
    if missing:
        raise SystemExit(f"Role map missing columns: {sorted(missing)}")
    lookup = {(str(r.source_group_id), str(r.speaker_cluster_id)): r for r in role_map.itertuples(index=False)}
    for column, default in {
        "witness_in_segment": "UNKNOWN",
        "witness_speaking_status": "UNKNOWN",
        "speaker_role": "UNKNOWN",
        "speaker_role_source": "unresolved",
        "speaker_role_confidence": "LOW",
        "visual_target_role": "UNKNOWN",
        "visual_speaker_match": "UNKNOWN",
    }.items():
        if column not in manifest.columns:
            manifest[column] = default
    applied = 0
    for index, row in manifest.iterrows():
        key = (str(row.get("youtube_id", "")), str(row.get("speaker_cluster_id", "UNKNOWN")))
        mapped = lookup.get(key)
        if mapped is None:
            continue
        role = str(getattr(mapped, "role_label", "") or "UNKNOWN").strip()
        confidence = str(getattr(mapped, "role_confidence", "") or "LOW").strip().upper()
        status = str(getattr(mapped, "witness_speaking_status", "") or "UNKNOWN").strip().upper()
        witness_in_segment = str(getattr(mapped, "witness_in_segment", "") or "UNKNOWN").strip().upper()
        if role not in VALID_ROLES:
            raise SystemExit(f"Invalid role {role!r} for {key}")
        if status not in VALID_STATUS:
            raise SystemExit(f"Invalid witness_speaking_status {status!r} for {key}")
        if witness_in_segment not in VALID_WITNESS_PRESENCE:
            raise SystemExit(f"Invalid witness_in_segment {witness_in_segment!r} for {key}")
        manifest.at[index, "speaker_role"] = role
        manifest.at[index, "speaker_role_source"] = "manual_verified_diarization"
        manifest.at[index, "speaker_role_confidence"] = confidence
        manifest.at[index, "witness_in_segment"] = witness_in_segment
        manifest.at[index, "witness_speaking_status"] = status
        manifest.at[index, "visual_target_role"] = str(getattr(mapped, "visual_target_role", "") or "UNKNOWN")
        manifest.at[index, "visual_speaker_match"] = str(getattr(mapped, "visual_speaker_match", "") or "UNKNOWN")
        if role == "Witness":
            manifest.at[index, "witness_in_segment"] = "YES"
        applied += 1
    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(out, index=False)
    print(f"Applied manual roles to {applied} rows; wrote {len(manifest)} rows to {out}")


if __name__ == "__main__":
    main()
