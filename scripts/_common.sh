#!/bin/bash
# _common.sh — 共通関数・変数（source して使う）

WORKDIR="${WORKDIR:-/var/share/yorusaro/src/ui_shisha_crm}"
DEFAULT_BRANCH="main"

die() { echo "ERROR: $*" >&2; exit 1; }

current_branch() {
  git rev-parse --abbrev-ref HEAD 2>/dev/null || die "Not a git repository"
}

require_clean_work() {
  local status
  status=$(git status --porcelain 2>/dev/null)
  [[ -z "$status" ]] || die "Working tree is dirty. Commit or stash changes first.\n$(echo "$status" | head -10)"
}

require_on_feature() {
  local branch
  branch=$(current_branch)
  [[ "$branch" != "$DEFAULT_BRANCH" && "$branch" != "main" ]] \
    || die "You are on $branch. Switch to a feature branch first."
}

bootstrap_env() {
  # Activate conda if available (yamatoro uses miniconda3)
  if [[ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    conda activate base 2>/dev/null
  # Fallback: root uses miniconda3 directly
  elif [[ -f /root/miniconda3/etc/profile.d/conda.sh ]]; then
    source /root/miniconda3/etc/profile.d/conda.sh
    conda activate base 2>/dev/null
  fi

  if [[ -f "${WORKDIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${WORKDIR}/.env"
    set +a
  fi
}
