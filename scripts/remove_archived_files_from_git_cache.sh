#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPLY=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/remove_archived_files_from_git_cache.sh [--apply]

Default mode is dry-run: it prints tracked archive files that would be removed
from the git index, but it does not modify the working tree.

Options:
  --apply    Actually run `git rm --cached` on the matched files.
  -h, --help Show this help message.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --apply)
      APPLY=1
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

cd "$ROOT_DIR"

MATCHED=()
while IFS= read -r path; do
  if [[ "$path" == *.zip || "$path" == *.tar.gz || "$path" == *.tgz ]]; then
    MATCHED+=("$path")
  fi
done < <(git ls-files)

echo "Repository root: $ROOT_DIR"
echo
if [[ "${#MATCHED[@]}" -eq 0 ]]; then
  echo "No tracked .zip, .tar.gz, or .tgz files found in the git index."
  exit 0
fi

echo "Tracked archive files currently in git:"
for path in "${MATCHED[@]}"; do
  printf '  %s\n' "$path"
done
echo

if [[ "$APPLY" -ne 1 ]]; then
  echo "Dry-run only. Re-run with --apply to remove these files from the git index."
  exit 0
fi

read -r -p "Type REMOVE to untrack the listed archive files: " confirm
if [[ "$confirm" != "REMOVE" ]]; then
  echo "Confirmation not received. Aborting."
  exit 1
fi

git rm --cached -- "${MATCHED[@]}"
echo "Removed tracked archive files from the git index."
