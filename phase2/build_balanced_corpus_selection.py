from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import ensure_dir
    from phase2.trimodal_validation_utils import csv_rows, csv_write, normalize_case_number, normalize_text
else:
    from .common import ensure_dir
    from .trimodal_validation_utils import csv_rows, csv_write, normalize_case_number, normalize_text


DISCOVERY_INPUT = Path("data/processed/phase2/paired_hearing_witness_discovery.csv")
HEARING_VALIDATED_INPUT = Path("data/processed/phase2/hearing_manifest_validated.csv")
OUTPUT_CSV = Path("data/processed/phase2/trimodal_corpus_selection.csv")
SUMMARY_OUTPUT = Path("reports/phase2/corpus_selection_summary.json")

TARGET_MIN_HOURS = 20.0
TARGET_MAX_HOURS = 30.0
TARGET_MIN_WITNESSES = 40
TARGET_MAX_WITNESSES = 50
TARGET_MIN_UTTERANCES = 10000
TARGET_MAX_UTTERANCES = 15000
WITNESS_MINUTE_CAP = 45.0
HEARING_MAX_SHARE = 0.60


def _load_map(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    for row in csv_rows(path):
        hearing_id = normalize_text(row.get("hearing_id"))
        if hearing_id:
            out[hearing_id] = row
    return out


def _selection_score(row: dict[str, str], pilot_map: dict[str, dict[str, str]]) -> float:
    score = 0.0
    status = normalize_text(row.get("witness_identity_status")).upper()
    if status == "PROTECTED_CODE":
        score += 45
    elif status == "PUBLIC_NAME":
        score += 42
    elif status == "MULTIPLE_WITNESSES":
        score += 20
    elif status == "UNRESOLVED_WITNESS":
        score += 5
    if row.get("transcript_readable") == "YES":
        score += 10
    if row.get("contains_actual_witness_testimony") == "YES":
        score += 20
    if "cross_examination" in normalize_text(row.get("examination_types_present")).lower():
        score += 6
    if "direct_examination" in normalize_text(row.get("examination_types_present")).lower():
        score += 5
    if "mixed" in normalize_text(row.get("examination_types_present")).lower():
        score += 3
    score += min(25.0, float(row.get("usable_witness_utterance_estimate") or 0) * 0.5)
    score += min(10.0, float(row.get("estimated_testimony_minutes") or 0) / 3.0)
    if row.get("is_repeat_witness") == "NO":
        score += 12
    else:
        score -= 6
    hearing_id = normalize_text(row.get("hearing_id"))
    if hearing_id in pilot_map:
        pilot = pilot_map[hearing_id]
        if pilot.get("media_validation_status") == "validated":
            score += 10
        if pilot.get("transcript_validation_status") == "validated":
            score += 5
        if pilot.get("final_trimodal_eligible") == "YES":
            score += 8
    if row.get("witness_resolution_confidence") == "high":
        score += 5
    elif row.get("witness_resolution_confidence") == "medium":
        score += 2
    if normalize_text(row.get("transcript_language")).upper() in {"ENG", "EN"}:
        score += 2
    return round(score, 2)


def _priority(score: float, new_witness: bool, repeat: bool) -> str:
    if not new_witness and repeat:
        return "LOW"
    if score >= 60:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def _batch_for_row(row: dict[str, str], selected: bool, pilot_map: dict[str, dict[str, str]]) -> str:
    hearing_id = normalize_text(row.get("hearing_id"))
    if hearing_id in pilot_map and pilot_map[hearing_id].get("final_trimodal_eligible") == "YES":
        return "PILOT_VALIDATED" if selected else "RESERVE"
    if selected and row.get("selection_priority") == "HIGH":
        return "BATCH_1_HIGH_PRIORITY"
    if selected and row.get("selection_priority") == "MEDIUM":
        return "BATCH_2_DIVERSITY"
    if selected:
        return "BATCH_2_DIVERSITY"
    return "RESERVE" if row.get("witness_identity_status") in {"PUBLIC_NAME", "PROTECTED_CODE", "MULTIPLE_WITNESSES"} else "REJECTED"


def _estimate_selected_minutes(row: dict[str, str]) -> float:
    utterances = float(row.get("usable_witness_utterance_estimate") or 0)
    turns = float(row.get("transcript_speaker_turns") or 0)
    estimate = max(12.0, min(WITNESS_MINUTE_CAP, utterances * 0.9 + turns * 0.1))
    return round(estimate, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a balanced corpus selection from transcript-first witness discovery")
    parser.add_argument("--discovery-input", default=str(DISCOVERY_INPUT))
    parser.add_argument("--hearing-validated-input", default=str(HEARING_VALIDATED_INPUT))
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV))
    parser.add_argument("--summary-output", default=str(SUMMARY_OUTPUT))
    args = parser.parse_args()

    discovery_rows = csv_rows(args.discovery_input)
    pilot_map = _load_map(Path(args.hearing_validated_input))

    # Collapse to one best candidate row per witness key where possible.
    by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in discovery_rows:
        key = normalize_text(row.get("witness_key"))
        if not key:
            key = "|".join(
                [
                    normalize_text(row.get("tribunal")).upper(),
                    normalize_case_number(row.get("case_number")).upper(),
                    normalize_text(row.get("witness_name_or_code")).upper(),
                    normalize_text(row.get("hearing_id")).upper(),
                ]
            )
        by_key[key].append(row)

    selected_keys: set[str] = set()
    selected_case_minutes: Counter[str] = Counter()
    selected_case_counts: Counter[str] = Counter()
    selected_case_families: set[str] = set()
    selected_witnesses: set[str] = set()
    total_minutes = 0.0
    total_utterances = 0
    selection_rows: list[dict[str, object]] = []

    ranked: list[tuple[float, dict[str, str], str]] = []
    for key, rows in by_key.items():
        best = max(rows, key=lambda r: _selection_score(r, pilot_map))
        score = _selection_score(best, pilot_map)
        ranked.append((score, best, key))
    ranked.sort(key=lambda item: (-item[0], normalize_case_number(item[1].get("case_number")), normalize_text(item[1].get("hearing_date"))))

    for score, row, key in ranked:
        case_family = normalize_text(row.get("case_family"))
        case_number = normalize_case_number(row.get("case_number"))
        hearing_id = normalize_text(row.get("hearing_id"))
        witness = normalize_text(row.get("witness_name_or_code"))
        status = normalize_text(row.get("witness_identity_status")).upper()
        estimated_minutes = _estimate_selected_minutes(row)
        estimated_utterances = int(float(row.get("usable_witness_utterance_estimate") or 0))
        new_witness = key not in selected_keys and status in {"PUBLIC_NAME", "PROTECTED_CODE"}
        repeat = row.get("is_repeat_witness") == "YES"
        priority = _priority(score, new_witness, repeat)

        hearing_share_after = (selected_case_minutes[case_family] + estimated_minutes) / (total_minutes + estimated_minutes) if total_minutes > 0 else 0.0
        projected_minutes = total_minutes + estimated_minutes
        if projected_minutes > TARGET_MAX_HOURS * 60:
            selected = False
        elif status not in {"PUBLIC_NAME", "PROTECTED_CODE", "MULTIPLE_WITNESSES"}:
            selected = False
        elif row.get("contains_actual_witness_testimony") != "YES":
            selected = False
        elif key in selected_keys and selected_case_minutes[case_family] >= WITNESS_MINUTE_CAP:
            selected = False
        else:
            selected = (
                projected_minutes <= TARGET_MAX_HOURS * 60
                and (
                    new_witness
                    or total_minutes < TARGET_MIN_HOURS * 60
                    or selected_case_counts[case_family] < 2
                    or status == "PROTECTED_CODE"
                )
            )

        selection_status = "SELECTED" if selected else "RESERVE"
        selected_for_download = "YES" if selected else "NO"
        requires_media_probe = "NO" if hearing_id in pilot_map and pilot_map[hearing_id].get("media_validation_status") == "validated" else "YES"
        requires_full_download = "YES" if selected else "NO"
        batch = _batch_for_row(row, selected, pilot_map)
        if selected:
            if key not in selected_keys and status in {"PUBLIC_NAME", "PROTECTED_CODE"}:
                selected_keys.add(key)
                selected_witnesses.add("|".join([normalize_text(row.get("tribunal")).upper(), case_number.upper(), witness.upper()]))
            total_minutes += estimated_minutes
            total_utterances += estimated_utterances
            selected_case_minutes[case_family] += estimated_minutes
            selected_case_counts[case_family] += 1
            selected_case_families.add(case_family)
        selection_rows.append(
            {
                **row,
                "selection_score": score,
                "selection_priority": priority,
                "selection_reason": (
                    "new_distinct_witness"
                    if new_witness
                    else "balanced_diversity"
                    if selected
                    else "reserve_or_duplicate"
                ),
                "requires_media_probe": requires_media_probe,
                "requires_full_download": requires_full_download,
                "selected_for_download": selected_for_download,
                "selected_start_marker": normalize_text(row.get("testimony_start_marker")),
                "selected_end_marker": normalize_text(row.get("testimony_end_marker")),
                "selected_estimated_minutes": estimated_minutes if selected else 0.0,
                "selected_estimated_utterances": estimated_utterances if selected else 0,
                "selection_batch": batch,
                "selection_status": selection_status,
            }
        )

    selection_rows.sort(
        key=lambda row: (
            0 if row.get("selected_for_download") == "YES" else 1,
            -float(row.get("selection_score") or 0),
            normalize_case_number(row.get("case_number")),
            normalize_text(row.get("hearing_date")),
        )
    )

    csv_write(
        args.output_csv,
        selection_rows,
        list(selection_rows[0].keys()) if selection_rows else [],
    )

    selected_rows = [row for row in selection_rows if row.get("selected_for_download") == "YES"]
    selected_hours = round(sum(float(row.get("selected_estimated_minutes") or 0) for row in selected_rows) / 60.0, 2)
    selected_utterances = sum(int(row.get("selected_estimated_utterances") or 0) for row in selected_rows)
    selected_distinct_witnesses = len({normalize_text(row.get("witness_key")) for row in selected_rows if normalize_text(row.get("witness_key"))})
    case_families_selected = len({normalize_text(row.get("case_family")) for row in selected_rows if normalize_text(row.get("case_family"))})
    summary = {
        "paired_hearings_scanned": len({normalize_text(row.get("hearing_id")) for row in discovery_rows if normalize_text(row.get("hearing_id"))}),
        "readable_transcripts": sum(1 for row in discovery_rows if row.get("transcript_readable") == "YES"),
        "hearings_with_witness_testimony": len({normalize_text(row.get("hearing_id")) for row in discovery_rows if row.get("contains_actual_witness_testimony") == "YES"}),
        "non_witness_hearings": len({normalize_text(row.get("hearing_id")) for row in discovery_rows if row.get("non_witness_hearing_reason")}),
        "public_witnesses_discovered": len({normalize_text(row.get("witness_key")) for row in discovery_rows if normalize_text(row.get("witness_identity_status")).upper() == "PUBLIC_NAME" and normalize_text(row.get("witness_key"))}),
        "protected_witnesses_discovered": len({normalize_text(row.get("witness_key")) for row in discovery_rows if normalize_text(row.get("witness_identity_status")).upper() == "PROTECTED_CODE" and normalize_text(row.get("witness_key"))}),
        "distinct_witnesses_discovered": len({normalize_text(row.get("witness_key")) for row in discovery_rows if normalize_text(row.get("witness_key"))}),
        "repeat_witness_hearings": len({normalize_text(row.get("hearing_id")) for row in discovery_rows if row.get("is_repeat_witness") == "YES"}),
        "unresolved_witness_hearings": len({normalize_text(row.get("hearing_id")) for row in discovery_rows if normalize_text(row.get("witness_identity_status")).upper() == "UNRESOLVED_WITNESS"}),
        "raw_witness_utterances": sum(int(row.get("raw_witness_utterance_count") or 0) for row in discovery_rows),
        "usable_witness_utterances_estimated": sum(int(row.get("usable_witness_utterance_estimate") or 0) for row in discovery_rows),
        "candidate_testimony_hours": round(sum(float(row.get("estimated_testimony_minutes") or 0) for row in discovery_rows) / 60.0, 2),
        "selected_hearings": len({normalize_text(row.get("hearing_id")) for row in selected_rows}),
        "selected_distinct_witnesses": selected_distinct_witnesses,
        "selected_estimated_hours": selected_hours,
        "selected_estimated_utterances": selected_utterances,
        "case_families_selected": case_families_selected,
        "target_hours_status": "within_target"
        if TARGET_MIN_HOURS <= selected_hours <= TARGET_MAX_HOURS
        else "below_target"
        if selected_hours < TARGET_MIN_HOURS
        else "above_target",
        "target_witnesses_status": "within_target"
        if TARGET_MIN_WITNESSES <= selected_distinct_witnesses <= TARGET_MAX_WITNESSES
        else "below_target"
        if selected_distinct_witnesses < TARGET_MIN_WITNESSES
        else "above_target",
        "target_utterances_status": "within_target"
        if TARGET_MIN_UTTERANCES <= selected_utterances <= TARGET_MAX_UTTERANCES
        else "below_target"
        if selected_utterances < TARGET_MIN_UTTERANCES
        else "above_target",
    }
    ensure_dir(Path(args.summary_output).parent)
    Path(args.summary_output).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(selection_rows)} selection rows to {args.output_csv}")
    print(f"Wrote summary to {args.summary_output}")


if __name__ == "__main__":
    main()
