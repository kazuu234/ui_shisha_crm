#!/bin/bash
# request-review.sh — Codex MCP レビュー用の review instruction を stdout に出力
#
# Usage:
#   ./scripts/request-review.sh
#   REVIEW=$(./scripts/request-review.sh)  # Opus が mcp__codex__codex に渡す
#
# stdout にレビュー指示を出力する。stderr にステータスを出す。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_common.sh"

MAX_DIFF_LINES="${MAX_DIFF_LINES:-3000}"
SCORECARD="${WORKDIR}/docs/framework/REVIEW_SCORECARD.md"

while [[ $# -gt 0 ]]; do
  case $1 in
    --help)
      echo "Usage: $0" >&2
      echo "Outputs review instruction to stdout for Codex MCP." >&2
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

cd "$WORKDIR"
require_on_feature

BRANCH=$(current_branch)
DIFF=$(git diff "${DEFAULT_BRANCH}..${BRANCH}")
DIFF_LINES=$(echo "$DIFF" | wc -l)

[[ "$DIFF_LINES" -gt 1 ]] || die "No diff between ${DEFAULT_BRANCH} and ${BRANCH}"
[[ -f "$SCORECARD" ]] || die "Scorecard not found: ${SCORECARD}"

SCORECARD_CONTENT=$(cat "$SCORECARD")

echo >&2 "request-review: ${BRANCH} (${DIFF_LINES} lines of diff)"

# Output review instruction to stdout
cat <<REVIEW
以下の diff を **REVIEW_SCORECARD** に基づいてレビューしてください。

- branch: ${BRANCH}
- base: origin/${DEFAULT_BRANCH}
- 対象: \`git diff origin/${DEFAULT_BRANCH}..${BRANCH}\`

## 重要なルール

- **PASS は 100/100 のみ**。99点以下は全て FAIL
- 必須ゲート（Stage 1）を1つでも満たさなければスコア上限は 99点
- runtime 確認が必要な項目は \`要 smoke test\` とマークし、**減点しない**
- 出力は下記フォーマットに厳密に従うこと

## 出力フォーマット（必須）

### Verdict
PASS または FAIL

### Score
XX/100（各カテゴリの内訳付き）

### Gate Check
必須ゲート6項目それぞれの判定結果（OK / NG / 確認不能）

### Findings
severity 順。file/path 明記。要件漏れ / 品質問題 / 統合漏れ を区別

### Smoke Test Items
\`要 smoke test\` としてマークした項目の一覧（あれば）

### Pushback
FAIL の場合、implementation subagent に返すべき修正指示

---

## 採点基準（REVIEW_SCORECARD）

${SCORECARD_CONTENT}

REVIEW

if [[ "$DIFF_LINES" -le "$MAX_DIFF_LINES" ]]; then
  cat <<DIFF_SECTION
## Diff

\`\`\`diff
${DIFF}
\`\`\`
DIFF_SECTION
else
  DIFF_STAT=$(git diff --stat "${DEFAULT_BRANCH}..${BRANCH}")
  cat <<DIFF_SECTION
## Diff (${DIFF_LINES} lines — stat のみ表示)

\`\`\`
${DIFF_STAT}
\`\`\`

全文は \`git diff origin/${DEFAULT_BRANCH}..${BRANCH}\` で確認してください。
DIFF_SECTION
fi
