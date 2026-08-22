#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bash phase2/run_discover_official_tribunal_source_broadening_candidates.sh "$@"
bash phase2/run_build_broadened_tribunal_source_manifest.sh --include-hold-for-link-validation "$@"
