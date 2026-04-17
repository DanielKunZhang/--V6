#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
message="checkpoint: ${timestamp}"
push_after_commit="false"

if [[ $# -ge 1 && "${1:-}" != "--push" ]]; then
  message="$1"
  shift
fi

if [[ $# -ge 1 && "${1:-}" == "--push" ]]; then
  push_after_commit="true"
fi

echo "== git status =="
git status --short

git add -A

if git diff --cached --quiet; then
  echo "No staged changes to commit."
  exit 0
fi

git commit -m "$message"

if [[ "$push_after_commit" == "true" ]]; then
  git push origin main
fi
