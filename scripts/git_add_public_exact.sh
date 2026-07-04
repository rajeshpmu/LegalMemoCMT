#!/usr/bin/env bash
set -euo pipefail

# Exact allowlist staging helper for the public LegalMemoCMT repo.
# This script stages only known-safe source, config, and manifest paths.
# It intentionally avoids all generated artifacts, raw data, results, and docs.

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "This script must be run inside a git repository." >&2
  exit 1
fi

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

ALLOWLIST=(
  "README.md"
  "README_NEW_BENCHMARK_APPROACH.md"
  "README_PAPER_EXACT.md"
  "README_PHASE1.md"
  "README_PRIMARY_BENCHMARKS_CV.md"
  "FIRST_SUBMISSION_CHECKLIST.md"
  "requirements-phase1.txt"
  "configs"
  "legalmemocmt_phase1"
  "scripts"
  "src"
  "data/manifests"
)

echo "Repository root: $ROOT_DIR"
echo "Staging only the explicit allowlist:"
for path in "${ALLOWLIST[@]}"; do
  printf '  - %s\n' "$path"
done

git add -- "${ALLOWLIST[@]}"

echo
echo "Staged paths:"
git diff --cached --name-only

echo
echo "Safety check:"
if git diff --cached --name-only | grep -E '^(data/[^m]|results/|implementation_docments/|artifacts/|backups/|submission_first/)' >/dev/null; then
  echo "ERROR: A forbidden path is staged. Unstage it before pushing." >&2
  exit 1
fi

echo "OK: no raw dataset or generated-artifact paths are staged."
