#!/usr/bin/env bash
set -euo pipefail

# Push helper for the public LegalMemoCMT repo.
# It stages only the intended source/config/manifest files and excludes
# generated artifacts, results, Word docs, and diagram exports.

REMOTE_NAME="${REMOTE_NAME:-origin}"
REMOTE_URL="${REMOTE_URL:-}"
BRANCH_NAME="${BRANCH_NAME:-$(git branch --show-current)}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Initial LegalMemoCMT source push}"

if [ -z "$BRANCH_NAME" ]; then
  echo "Unable to determine the current branch. Set BRANCH_NAME manually." >&2
  exit 1
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "This script must be run inside a git repository." >&2
  exit 1
fi

if ! git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
  if [ -n "$REMOTE_URL" ]; then
    git remote add "$REMOTE_NAME" "$REMOTE_URL"
    echo "Added remote $REMOTE_NAME -> $REMOTE_URL"
  else
    echo "Remote '$REMOTE_NAME' is not configured." >&2
    echo "Set REMOTE_URL or add the remote manually, for example:" >&2
    echo "  git remote add $REMOTE_NAME https://github.com/rajeshpmu/LegalMemoCMT.git" >&2
    exit 1
  fi
fi

git add \
  README.md \
  README_NEW_BENCHMARK_APPROACH.md \
  README_PAPER_EXACT.md \
  README_PHASE1.md \
  README_PRIMARY_BENCHMARKS_CV.md \
  FIRST_SUBMISSION_CHECKLIST.md \
  requirements-phase1.txt \
  configs \
  legalmemocmt_phase1 \
  notebooks \
  scripts \
  src \
  data/manifests

echo "Staged files:"
git status --short

if git diff --cached --quiet; then
  echo "Nothing to commit."
else
  git commit -m "$COMMIT_MESSAGE"
fi

git push "$REMOTE_NAME" "$BRANCH_NAME"
