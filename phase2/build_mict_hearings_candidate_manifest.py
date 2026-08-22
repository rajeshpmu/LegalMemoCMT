from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import write_csv
else:
    from .common import write_csv


DEFAULT_OUTPUT = Path("data/processed/phase2/mict_hearings_candidate_manifest.csv")
DEFAULT_SUMMARY = Path("reports/phase2/mict_hearings_candidate_manifest_summary.json")


def build_rows() -> list[dict[str, object]]:
    # These candidates are grounded in official MICT case pages and should
    # replace the generic "IRMCT Hearings" placeholder row with specific
    # case numbers that can be inspected separately.
    return [
        {
            "candidate_id": "mict_kabuga_01",
            "tribunal": "MICT",
            "case_name": "Kabuga, Félicien",
            "case_number": "MICT-13-38",
            "case_stage": "trial",
            "hearing_or_proceeding_type": "status conference / trial proceedings",
            "public_evidence_url": "https://www.irmct.org/en/cases/mict-13-38",
            "why_selected": "Official case page shows active proceedings and courtroom broadcast coverage.",
            "recommended_use": "not_usable",
            "notes": "Not usable for the current Phase 2 corpus because the public page is not evidence of a witness-testimony clip that should be promoted directly.",
        },
        {
            "candidate_id": "mict_stanisic_simatovic_01",
            "tribunal": "MICT",
            "case_name": "Stanišić and Simatović",
            "case_number": "MICT-15-96",
            "case_stage": "appeal / completed trial record",
            "hearing_or_proceeding_type": "trial and appeal proceedings",
            "public_evidence_url": "https://www.irmct.org/en/cases/mict-15-96",
            "why_selected": "Official page reports 51 prosecution witnesses and 29 defence witnesses, so it is a strong hearing-heavy MICT case.",
            "recommended_use": "not_usable",
            "notes": "Not usable as a Phase 2 witness-testimony promotion row yet because the manifest only proves case-level hearing activity, not a grounded clip that should enter the corpus.",
        },
        {
            "candidate_id": "mict_ngirabatware_01",
            "tribunal": "MICT",
            "case_name": "Ngirabatware, Augustin",
            "case_number": "MICT-12-29",
            "case_stage": "review / completed appeal record",
            "hearing_or_proceeding_type": "review hearing",
            "public_evidence_url": "https://www.irmct.org/en/cases/mict-12-29",
            "why_selected": "Official page states that two witnesses renounced recantations at the review hearing, so the hearing record is explicit and well grounded.",
            "recommended_use": "not_usable",
            "notes": "Not usable for the current corpus target because review-hearing material is not the same as a promotable witness-testimony clip.",
        },
        {
            "candidate_id": "mict_ntakirutimana_01",
            "tribunal": "MICT",
            "case_name": "Ntakirutimana, Gérard",
            "case_number": "MICT-12-17-R",
            "case_stage": "review",
            "hearing_or_proceeding_type": "review hearing",
            "public_evidence_url": "https://www.irmct.org/en/cases/mict-12-17-r",
            "why_selected": "Official page announces a scheduled review hearing, making it a specific hearing identifier rather than a generic label.",
            "recommended_use": "not_usable",
            "notes": "Not usable for Phase 2 corpus promotion because the page establishes a review proceeding, not a verified witness-testimony clip.",
        },
        {
            "candidate_id": "mict_jojic_radeta_01",
            "tribunal": "MICT",
            "case_name": "Jojić and Radeta",
            "case_number": "MICT-17-111-R90",
            "case_stage": "contempt",
            "hearing_or_proceeding_type": "contempt proceedings",
            "public_evidence_url": "https://www.irmct.org/en/cases/mict-17-111-r90",
            "why_selected": "The official case page shows the named contempt matter as a concrete MICT case, so it is a specific proceeding row rather than a generic placeholder.",
            "recommended_use": "not_usable",
            "notes": "Not usable for witness-testimony corpus growth because this is a control/proceeding matter, not a testimony-bearing clip source.",
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a small MICT hearings candidate manifest from official case pages.")
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT), help="Output CSV")
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY), help="Summary JSON")
    args = parser.parse_args()

    rows = build_rows()
    output_path = Path(args.output_csv)
    write_csv(
        output_path,
        rows,
        [
            "candidate_id",
            "tribunal",
            "case_name",
            "case_number",
            "case_stage",
            "hearing_or_proceeding_type",
            "public_evidence_url",
            "why_selected",
            "recommended_use",
            "notes",
        ],
    )

    summary = {
        "output_csv": str(output_path),
        "rows_written": len(rows),
        "usable_rows": 0,
        "not_usable_rows": len(rows),
        "candidate_case_numbers": [row["case_number"] for row in rows],
        "candidate_case_names": [row["case_name"] for row in rows],
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
