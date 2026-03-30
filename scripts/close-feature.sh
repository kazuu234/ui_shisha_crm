#!/bin/bash
# close-feature.sh — review PASS 後の merge + branch 削除
#
# Usage:
#   ./scripts/close-feature.sh
#   ./scripts/close-feature.sh --reviewer "gpt-5.4 high" --score 95

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

REVIEWER=""
SCORE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --reviewer) REVIEWER="$2"; shift 2 ;;
    --score)    SCORE="$2"; shift 2 ;;
    --help)
      echo "Usage: $0 [--reviewer <name>] [--score <number>]"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

cd "$WORKDIR"
require_on_feature

BRANCH=$(current_branch)
require_clean_work

# Score gate: 100 未満は merge 禁止
if [[ -n "$SCORE" && "$SCORE" -lt 100 ]]; then
  die "Score ${SCORE}/100 — merge requires PASS (100/100). Fix findings and re-review."
fi

echo "=== close-feature: ${BRANCH} ==="

# Build merge message
MERGE_MSG="merge: ${BRANCH}"
if [[ -n "$SCORE" && -n "$REVIEWER" ]]; then
  MERGE_MSG="merge: ${BRANCH} (PASS ${SCORE}/100, reviewer: ${REVIEWER})"
fi

# Switch to default branch and update
git checkout "$DEFAULT_BRANCH"
git pull origin "$DEFAULT_BRANCH"

# Merge feature branch
echo "--- Merging ${BRANCH} → ${DEFAULT_BRANCH} ---"
git merge --no-ff "$BRANCH" -m "$MERGE_MSG"

# Push
git push origin "$DEFAULT_BRANCH"
echo "  Pushed ${DEFAULT_BRANCH}"

# Delete feature branch (local + remote)
echo "--- Cleanup ---"
git branch -d "$BRANCH"
echo "  Deleted local branch: ${BRANCH}"

git push origin --delete "$BRANCH" 2>/dev/null \
  && echo "  Deleted remote branch: ${BRANCH}" \
  || echo "  WARNING: Could not delete remote branch ${BRANCH}"

echo ""
echo "=== close-feature complete ==="
echo "Merged: ${BRANCH} → ${DEFAULT_BRANCH}"
echo ""
echo "git log --oneline -5:"
git log --oneline -5
