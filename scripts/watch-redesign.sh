#!/bin/bash
# watch-redesign.sh — Issue コメントの再設計依頼/完了を監視して相手セッションに通知
#
# Usage:
#   ./scripts/watch-redesign.sh &
#   ./scripts/watch-redesign.sh --orchestrator-session ticket --design-session ticketdesign
#
# 前提:
#   - orchestrator が feature branch (feat/issueNN-xxx) 上で作業中
#   - tmux セッション名がわかっている
#   - gh CLI が認証済み

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

ORCHESTRATOR_SESSION=""
DESIGN_SESSION=""
INTERVAL="${INTERVAL:-180}"  # 秒（デフォルト3分）

while [[ $# -gt 0 ]]; do
  case $1 in
    --orchestrator-session) ORCHESTRATOR_SESSION="$2"; shift 2 ;;
    --design-session) DESIGN_SESSION="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --help)
      echo "Usage: $0 --orchestrator-session NAME --design-session NAME [--interval SECONDS]" >&2
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -n "$ORCHESTRATOR_SESSION" ]] || die "--orchestrator-session は必須です"
[[ -n "$DESIGN_SESSION" ]] || die "--design-session は必須です"

# セッション存在チェック
tmux has-session -t "$ORCHESTRATOR_SESSION" 2>/dev/null || die "tmux session '${ORCHESTRATOR_SESSION}' が見つかりません"
tmux has-session -t "$DESIGN_SESSION" 2>/dev/null || die "tmux session '${DESIGN_SESSION}' が見つかりません"

SEEN_FILE="/tmp/watch-redesign-seen-${ORCHESTRATOR_SESSION}.txt"

touch "$SEEN_FILE"

log() {
  echo "[watch-redesign $(date '+%H:%M:%S')] $*" >&2
}

send_to_session() {
  local session="$1"
  local message="$2"

  # idle チェック: プロンプト (❯) が表示されているか
  local pane_content
  pane_content=$(tmux capture-pane -t "$session" -p -S -3 2>/dev/null || echo "")

  if echo "$pane_content" | grep -q "❯"; then
    # idle — 直接送る
    tmux send-keys -t "$session" "$message" Enter
    log "Sent to ${session} (idle)"
  else
    # busy — ペンディングファイルに書く
    local pending="/tmp/watch-redesign-pending-${session}.txt"
    echo "$message" >> "$pending"
    log "Queued to ${session} (busy): $pending"
  fi
}

flush_pending() {
  local session="$1"
  local pending="/tmp/watch-redesign-pending-${session}.txt"

  [[ -f "$pending" ]] || return 0

  local pane_content
  pane_content=$(tmux capture-pane -t "$session" -p -S -3 2>/dev/null || echo "")

  if echo "$pane_content" | grep -q "❯"; then
    while IFS= read -r line; do
      tmux send-keys -t "$session" "$line" Enter
      sleep 2
    done < "$pending"
    rm -f "$pending"
    log "Flushed pending to ${session}"
  fi
}

check_issue() {
  cd "$WORKDIR"

  # feature branch から Issue 番号を取得
  local branch
  branch=$(git branch --show-current 2>/dev/null || echo "")
  local issue_num
  issue_num=$(echo "$branch" | grep -oP 'issue\K\d+' || echo "")

  if [[ -z "$issue_num" ]]; then
    return 0
  fi

  # Issue のコメントを取得
  local comments
  comments=$(gh issue view "$issue_num" --json comments --jq '.comments[] | "\(.createdAt)\t\(.body)"' 2>/dev/null || echo "")

  if [[ -z "$comments" ]]; then
    return 0
  fi

  # 🔄 再設計依頼 を検出 → design に通知
  echo "$comments" | while IFS=$'\t' read -r created_at body; do
    local key="request:${issue_num}:${created_at}"
    if echo "$body" | grep -q "🔄 再設計依頼" && ! grep -qF "$key" "$SEEN_FILE"; then
      echo "$key" >> "$SEEN_FILE"
      send_to_session "$DESIGN_SESSION" "Issue #${issue_num} に再設計依頼が来ています。 gh issue view ${issue_num} --comments で確認してください。"
    fi
  done

  # 📋 再設計完了 を検出 → orchestrator に通知
  echo "$comments" | while IFS=$'\t' read -r created_at body; do
    local key="response:${issue_num}:${created_at}"
    if echo "$body" | grep -q "📋 再設計完了" && ! grep -qF "$key" "$SEEN_FILE"; then
      echo "$key" >> "$SEEN_FILE"
      send_to_session "$ORCHESTRATOR_SESSION" "Issue #${issue_num} の再設計が完了しました。 gh issue view ${issue_num} --comments で更新内容を確認してください。"
    fi
  done
}

log "Started: orchestrator=${ORCHESTRATOR_SESSION}, design=${DESIGN_SESSION}, interval=${INTERVAL}s"
log "Watching feature branch for issue comments..."

while true; do
  check_issue
  flush_pending "$ORCHESTRATOR_SESSION"
  flush_pending "$DESIGN_SESSION"
  sleep "$INTERVAL"
done
