#!/bin/bash
# verify.sh — feature branch の実装を検証（Django check + テスト + diff stats）
#
# Usage:
#   ./scripts/verify.sh
#   ./scripts/verify.sh --test-args "tickets.tests.CheckinTests"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

TEST_ARGS=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --test-args) TEST_ARGS="$2"; shift 2 ;;
    --help)
      echo "Usage: $0 [--test-args <test-label>]"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

cd "$WORKDIR"
require_on_feature

BRANCH=$(current_branch)
ERRORS=0

echo "=== verify: ${BRANCH} ==="
echo ""

# Step 1: Django system check
echo "--- Step 1: manage.py check ---"
bootstrap_env

if python manage.py check 2>&1; then
  echo "  OK"
else
  echo "  FAIL"
  ERRORS=$((ERRORS + 1))
fi

echo ""

# Step 2: Test bundle
echo "--- Step 2: Tests ---"

if [[ -n "$TEST_ARGS" ]]; then
  TEST_CMD="python manage.py test --noinput ${TEST_ARGS}"
else
  TEST_CMD="python manage.py test --noinput"
fi

if eval "$TEST_CMD" 2>&1; then
  echo "  OK"
else
  echo "  FAIL"
  ERRORS=$((ERRORS + 1))
fi

echo ""

# Step 3: Diff stats
echo "--- Step 3: Diff stats (${DEFAULT_BRANCH}..${BRANCH}) ---"
git diff --stat "${DEFAULT_BRANCH}..${BRANCH}" 2>/dev/null || echo "(diff not available)"

echo ""

# Summary
if [[ $ERRORS -eq 0 ]]; then
  echo "=== ALL PASS ==="
else
  echo "=== FAIL (${ERRORS} step(s) failed) ==="
fi

echo ""
echo "Next: ./scripts/request-review.sh"

exit "$ERRORS"
