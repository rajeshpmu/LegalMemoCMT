EXTRA_LEDGER_ARGS="--extra-ledger-csv  data/phase2/source_manifests/case_candidate_ledger_ucr_enriched.csv --extra-ledger-csv data/phase2/source_manifests/tribunal_manifest_from_ledger.csv --extra-ledger-csv data/phase2/source_manifests/witness_manifest_from_ledger.csv" \
bash phase2/run_enrich_case_ledger_from_ucr_site.sh
