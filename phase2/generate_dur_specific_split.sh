PYTHON_BIN=$PWD/.venv/bin/python \
INPUT_CSV=$PWD/data/processed/phase2/clancy/clancy_turn_manifest_0_8_to_20.csv \
OUTPUT_CSV=$PWD/data/processed/phase2/clancy/duration_0_8_to_20/clancy_dataset_manifest.csv \
TRAIN_CSV=$PWD/data/processed/phase2/clancy/duration_0_8_to_20/train.csv \
DEV_CSV=$PWD/data/processed/phase2/clancy/duration_0_8_to_20/dev.csv \
TEST_CSV=$PWD/data/processed/phase2/clancy/duration_0_8_to_20/test.csv \
SUMMARY_JSON=$PWD/reports/phase2/clancy_duration_0_8_to_20_split_summary.json \
bash phase2/run_build_clancy_dataset_split.sh

PYTHON_BIN=$PWD/.venv/bin/python \
INPUT_CSV=$PWD/data/processed/phase2/clancy/clancy_turn_manifest_20_to_30.csv \
OUTPUT_CSV=$PWD/data/processed/phase2/clancy/duration_20_to_30/clancy_dataset_manifest.csv \
TRAIN_CSV=$PWD/data/processed/phase2/clancy/duration_20_to_30/train.csv \
DEV_CSV=$PWD/data/processed/phase2/clancy/duration_20_to_30/dev.csv \
TEST_CSV=$PWD/data/processed/phase2/clancy/duration_20_to_30/test.csv \
SUMMARY_JSON=$PWD/reports/phase2/clancy_duration_20_to_30_split_summary.json \
bash phase2/run_build_clancy_dataset_split.sh
