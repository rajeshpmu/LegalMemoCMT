#!/usr/bin/env bash
set -euo pipefail

# Force-add only the specific raw MELD test clips approved for demo use.
# This script does not stage any other raw data or generated artifacts.

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "This script must be run inside a git repository." >&2
  exit 1
fi

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

CLIPS=(
  "data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia279_utt9.mp4"
  "data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia278_utt5.mp4"
  "data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia143_utt2.mp4"
  "data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia244_utt14.mp4"
  "data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia153_utt5.mp4"
)

echo "Repository root: $ROOT_DIR"
echo "Force-staging only the approved demo clips:"
for clip in "${CLIPS[@]}"; do
  if [ ! -f "$clip" ]; then
    echo "Missing file: $clip" >&2
    exit 1
  fi
  printf '  - %s\n' "$clip"
done

git add -f -- "${CLIPS[@]}"

echo
echo "Staged files:"
git diff --cached --name-only -- "${CLIPS[@]}"

echo
echo "Safety check:"
if git diff --cached --name-only | grep -E '^(data/|results/|implementation_docments/)' | grep -v '^data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/(dia279_utt9|dia278_utt5|dia143_utt2|dia244_utt14|dia153_utt5)\.mp4$' >/dev/null; then
  echo "ERROR: Unexpected data/results/document path is staged." >&2
  exit 1
fi

echo "OK: only the approved demo clips were staged."
