from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


VALID_ROLES = {"Witness", "Prosecutor", "Defence", "Judge", "Other", "UNKNOWN"}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
VALID_STATUS = {"SPEAKING", "LISTENING_OR_ADDRESSED", "UNKNOWN"}
VALID_PRESENCE = {"YES", "NO", "UNKNOWN"}


def value(row, name: str, default: str) -> str:
    raw = getattr(row, name, default)
    return str(raw or default).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply an incremental source-local Clancy speaker-cluster role map"
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--mapping-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    manifest = pd.read_csv(args.input_csv, dtype=str).fillna("")
    mapping = pd.read_csv(args.mapping_csv, dtype=str).fillna("")
    required = {"source_group_id", "speaker_cluster_id", "role_label", "role_confidence"}
    missing = required - set(mapping.columns)
    if missing:
        raise SystemExit(f"Mapping CSV missing columns: {sorted(missing)}")

    duplicate_keys = mapping.duplicated(["source_group_id", "speaker_cluster_id"], keep=False)
    if duplicate_keys.any():
        keys = mapping.loc[duplicate_keys, ["source_group_id", "speaker_cluster_id"]]
        raise SystemExit(f"Duplicate mapping keys found:\n{keys.to_string(index=False)}")

    for column, default in {
        "witness_in_segment": "UNKNOWN",
        "witness_speaking_status": "UNKNOWN",
        "speaker_role": "UNKNOWN",
        "speaker_role_source": "unresolved",
        "speaker_role_confidence": "LOW",
        "visual_target_role": "UNKNOWN",
        "visual_speaker_match": "UNKNOWN",
        "role_mapping_notes": "",
        "corpus_exclusion_status": "",
        "corpus_exclusion_reason": "",
    }.items():
        if column not in manifest.columns:
            manifest[column] = default

    lookup = {
        (str(row.source_group_id), str(row.speaker_cluster_id)): row
        for row in mapping.itertuples(index=False)
    }
    applied = 0
    unmatched_mapping_keys: set[tuple[str, str]] = set(lookup)
    for index, raw in manifest.iterrows():
        key = (str(raw.get("youtube_id", "")), str(raw.get("speaker_cluster_id", "UNKNOWN")))
        mapped = lookup.get(key)
        if mapped is None:
            continue
        unmatched_mapping_keys.discard(key)
        role = value(mapped, "role_label", "UNKNOWN")
        confidence = value(mapped, "role_confidence", "LOW").upper()
        presence = value(mapped, "witness_in_segment", "UNKNOWN").upper()
        status = value(mapped, "witness_speaking_status", "UNKNOWN").upper()
        if role not in VALID_ROLES:
            raise SystemExit(f"Invalid role {role!r} for {key}")
        if confidence not in VALID_CONFIDENCE:
            raise SystemExit(f"Invalid role confidence {confidence!r} for {key}")
        if presence not in VALID_PRESENCE:
            raise SystemExit(f"Invalid witness presence {presence!r} for {key}")
        if status not in VALID_STATUS:
            raise SystemExit(f"Invalid witness speaking status {status!r} for {key}")

        manifest.at[index, "speaker_role"] = role
        manifest.at[index, "speaker_role_source"] = "manual_verified_diarization"
        manifest.at[index, "speaker_role_confidence"] = confidence
        manifest.at[index, "witness_in_segment"] = presence
        manifest.at[index, "witness_speaking_status"] = status
        manifest.at[index, "visual_target_role"] = value(mapped, "visual_target_role", "UNKNOWN")
        manifest.at[index, "visual_speaker_match"] = value(mapped, "visual_speaker_match", "UNKNOWN")
        manifest.at[index, "role_mapping_notes"] = value(mapped, "review_notes", "")
        exclusion_status = value(mapped, "corpus_exclusion_status", "").upper()
        if exclusion_status not in {"", "INCLUDE", "EXCLUDE"}:
            raise SystemExit(f"Invalid corpus exclusion status {exclusion_status!r} for {key}")
        manifest.at[index, "corpus_exclusion_status"] = exclusion_status
        manifest.at[index, "corpus_exclusion_reason"] = value(mapped, "corpus_exclusion_reason", "")
        applied += 1

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(output, index=False)
    print(f"Applied {applied} manifest rows from {len(mapping)} mapping rows")
    print(f"Wrote {len(manifest)} rows to {output}")
    if unmatched_mapping_keys:
        print(f"WARNING: mapping keys not present in input: {sorted(unmatched_mapping_keys)}")


if __name__ == "__main__":
    main()
