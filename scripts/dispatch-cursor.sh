#!/bin/bash
# dispatch-cursor.sh — Cursor agent (headless subprocess) に実装指示を送る
#
# Usage:
#   ./scripts/dispatch-cursor.sh --prompt-file /tmp/instruction.md
#   ./scripts/dispatch-cursor.sh --prompt "Fix the login bug"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

PROMPT=""
PROMPT_FILE=""
LOG_DIR="/tmp/opus-logs"

while [[ $# -gt 0 ]]; do
  case $1 in
    --prompt-file) PROMPT_FILE="$2"; shift 2 ;;
    --prompt)      PROMPT="$2"; shift 2 ;;
    --help)
      echo "Usage: $0 --prompt-file <file> | --prompt <text>"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -n "$PROMPT" || -n "$PROMPT_FILE" ]] || die "Either --prompt or --prompt-file is required"

cd "$WORKDIR"
require_on_feature

BRANCH=$(current_branch)

# Load prompt content
if [[ -n "$PROMPT_FILE" ]]; then
  [[ -f "$PROMPT_FILE" ]] || die "Prompt file not found: $PROMPT_FILE"
  PROMPT_CONTENT=$(cat "$PROMPT_FILE")
else
  PROMPT_CONTENT="$PROMPT"
fi

# Build preamble
PREAMBLE="Work in \`${WORKDIR}\` on branch \`${BRANCH}\`.

Before editing, read these project rules:
- \`${WORKDIR}/CLAUDE.md\`

For any Django command, load the environment first:

\`\`\`bash
if [ -f \"${WORKDIR}/.env\" ]; then
  set -a
  source \"${WORKDIR}/.env\"
  set +a
fi
\`\`\`

---

"

FULL_PROMPT="${PREAMBLE}${PROMPT_CONTENT}"

# Ensure log directory exists
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/cursor-${BRANCH//\//-}-$(date +%Y%m%d-%H%M%S).log"

echo "=== dispatch-cursor: ${BRANCH} ==="
echo "=== Log: ${LOG_FILE} ==="
echo ""

# Launch cursor agent as headless subprocess (--yolo = auto-approve all edits)
PROMPT_FILE_TMP=$(mktemp /tmp/dispatch-prompt-XXXXXX.md)
echo "$FULL_PROMPT" > "$PROMPT_FILE_TMP"

if command -v agent &>/dev/null; then
  agent --yolo < "$PROMPT_FILE_TMP" 2>&1 | tee "$LOG_FILE"
  EXIT_CODE=${PIPESTATUS[0]}
else
  die "agent command not found (Cursor CLI). Is Cursor installed?"
fi

rm -f "$PROMPT_FILE_TMP"

echo ""
echo "=== dispatch-cursor complete ==="
echo "Exit code: ${EXIT_CODE}"
echo "Log:       ${LOG_FILE}"
echo ""
echo "Next: ./scripts/verify.sh"

exit "$EXIT_CODE"
