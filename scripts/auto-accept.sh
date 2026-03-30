#!/bin/bash
# auto-accept.sh — tmux ペインを監視し、Claude の "Accept" プロンプトに自動で Enter を送る
#
# Usage:
#   ./scripts/auto-accept.sh <session:window.pane> [interval_sec]
#
# Examples:
#   ./scripts/auto-accept.sh shishaorc:0.0
#   ./scripts/auto-accept.sh shishaorc:0.0 2
#   ./scripts/auto-accept.sh all          # 全ペインを監視

set -euo pipefail

INTERVAL="${2:-3}"
LAST_SENT=""

check_and_accept() {
  local target="$1"
  local content
  content=$(tmux capture-pane -t "$target" -p 2>/dev/null | tail -10) || return 1

  # "❯ Accept" が表示されていれば Enter を送る
  if echo "$content" | grep -q '❯ Accept'; then
    # 同じプロンプトに二重送信しないよう fingerprint で判定
    local fingerprint
    fingerprint=$(echo "$content" | grep -B5 '❯ Accept' | head -3 | md5sum | cut -d' ' -f1)
    if [[ "$fingerprint" != "${LAST_SENT_MAP[$target]:-}" ]]; then
      tmux send-keys -t "$target" Enter
      LAST_SENT_MAP["$target"]="$fingerprint"
      echo "[$(date '+%H:%M:%S')] ✓ Accept sent → $target"
    fi
  fi
}

declare -A LAST_SENT_MAP

echo "=== auto-accept: monitoring started (interval=${INTERVAL}s) ==="

if [[ "${1:-}" == "all" ]]; then
  echo "Mode: all panes"
  while true; do
    while IFS= read -r pane; do
      check_and_accept "$pane"
    done < <(tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index}' 2>/dev/null)
    sleep "$INTERVAL"
  done
else
  TARGET="${1:?Usage: $0 <session:window.pane|all> [interval_sec]}"
  echo "Target: $TARGET"
  while true; do
    check_and_accept "$TARGET"
    sleep "$INTERVAL"
  done
fi
