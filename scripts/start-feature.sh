#!/bin/bash
# start-feature.sh — feature branch を作成し、draft PR を開く
#
# Usage:
#   ./scripts/start-feature.sh --branch feat/69-script-redesign
#   ./scripts/start-feature.sh --branch fix/70-qr-bug --title "Fix QR display" --body "Resolves #70"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

BRANCH=""
PR_TITLE=""
PR_BODY=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --branch) BRANCH="$2"; shift 2 ;;
    --title)  PR_TITLE="$2"; shift 2 ;;
    --body)   PR_BODY="$2"; shift 2 ;;
    --help)
      echo "Usage: $0 --branch <branch-name> [--title <PR title>] [--body <PR body>]"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -n "$BRANCH" ]] || die "--branch is required"

cd "$WORKDIR"
require_clean_work

echo "=== start-feature: ${BRANCH} ==="

# Ensure we're on the default branch and up to date
git checkout "$DEFAULT_BRANCH"
git pull origin "$DEFAULT_BRANCH"

# Create and switch to feature branch
git checkout -b "$BRANCH"

# Push to remote
git push -u origin "$BRANCH"

echo "  Branch created: ${BRANCH}"

# Create draft PR if gh is available
if command -v gh &>/dev/null; then
  if [[ -z "$PR_TITLE" ]]; then
    PR_TITLE="$BRANCH"
  fi
  PR_URL=$(gh pr create --draft --title "$PR_TITLE" --body "${PR_BODY:-WIP}" 2>/dev/null) \
    && echo "  Draft PR: ${PR_URL}" \
    || echo "  WARNING: gh pr create failed (auth issue?). Create PR manually."
else
  echo "  NOTE: gh not available. Create PR manually."
fi

echo ""
echo "=== Done ==="
echo "Next: ./scripts/dispatch-cursor.sh --prompt-file <instruction>"
