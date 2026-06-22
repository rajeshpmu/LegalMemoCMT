#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

APPLY=0
KEEP_CREMA=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/prune_workspace_strict.sh [--apply] [--keep-crema]

Default mode is dry-run: it only prints what would be deleted.

Options:
  --apply       Actually delete the listed paths.
  --keep-crema   Keep CREMA-D results/manifests instead of marking them for deletion.
  -h, --help    Show this help message.
EOF
}

DELETE_PATHS=(
  "results/improvement"
  "results/phase1_ablation"
  "results/meld_case_study"
  "results/phase1"
  "results/phase1_small"
  "results/phase1_small_eval"
  "results/primary_conversational"
)

KEEP_PATHS=(
  "results/paper_aligned_meld_cv"
  "data/manifests/meld_raw.csv"
  "data/manifests/meld_cv"
  "data/manifests/meld_train.csv"
  "data/manifests/meld_dev.csv"
  "data/manifests/meld_test.csv"
)

CREMA_PATHS=(
  "results/paper_aligned_crema_d"
  "results/primary_speech_emotion"
  "data/manifests/crema_d.csv"
  "data/manifests/crema_d_cv"
)

for arg in "$@"; do
  case "$arg" in
    --apply)
      APPLY=1
      ;;
    --keep-crema)
      KEEP_CREMA=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$KEEP_CREMA" -eq 1 ]]; then
  for path in "${CREMA_PATHS[@]}"; do
    KEEP_PATHS+=("$path")
  done
else
  DELETE_PATHS+=("${CREMA_PATHS[@]}")
fi

echo "Workspace root: $ROOT_DIR"
echo
echo "Keep list:"
for path in "${KEEP_PATHS[@]}"; do
  echo "  KEEP  $path"
done
echo
echo "Delete list:"
for path in "${DELETE_PATHS[@]}"; do
  echo "  DEL   $path"
done
echo

if [[ "$APPLY" -ne 1 ]]; then
  echo "Dry-run only. Re-run with --apply to delete the listed paths."
  exit 0
fi

read -r -p "Type DELETE to confirm permanent removal of the listed paths: " confirm
if [[ "$confirm" != "DELETE" ]]; then
  echo "Confirmation not received. Aborting."
  exit 1
fi

for rel in "${DELETE_PATHS[@]}"; do
  target="$ROOT_DIR/$rel"
  if [[ -e "$target" ]]; then
    rm -rf "$target"
    echo "Deleted: $rel"
  else
    echo "Skipped missing path: $rel"
  fi
done

echo "Prune complete."
