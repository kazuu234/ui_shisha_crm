#!/bin/bash
# start-logging.sh — tmux セッションの全出力をファイルに記録開始
#
# Usage:
#   ./scripts/start-logging.sh              # default: tickets session
#   ./scripts/start-logging.sh composer      # composer session
#   ./scripts/start-logging.sh tickets 0     # specific pane
#
# 出力先: /tmp/opus-logs/<session>-<date>.log
# 停止:   tmux pipe-pane -t <session>:0

set -euo pipefail

SESSION="${1:-tickets}"
PANE="${2:-0}"
TARGET="${SESSION}:${PANE}"
LOG_DIR="/tmp/opus-logs"

mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/${SESSION}-$(date +%Y%m%d-%H%M%S).log"

# Stop existing pipe-pane before starting
tmux pipe-pane -t "$TARGET" "" 2>/dev/null || true
tmux pipe-pane -t "$TARGET" "cat >> '${LOG_FILE}'"

echo "=== Session logging started ==="
echo "Session: ${TARGET}"
echo "Log:     ${LOG_FILE}"
echo ""
echo "Stop:    tmux pipe-pane -t ${TARGET}"
