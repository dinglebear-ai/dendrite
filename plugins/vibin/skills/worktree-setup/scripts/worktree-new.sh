#!/usr/bin/env bash
# worktree-new.sh — create a worktree under .worktrees/<slug> in the repo and
# immediately sync it warm, so it is non-degraded from the first command.
#
# This is the canonical "create a worktree" entrypoint for our workflow. It
# always places worktrees in <repo>/.worktrees/, creates/uses the branch, makes
# sure .worktrees/ is git-ignored, then runs worktree-sync.sh to bring over
# secrets, local config, warm caches, and tool-trust state.
#
# Before creating, it runs a read-only pre-flight: warns if the current checkout
# has uncommitted changes (and how to carry them), lists existing worktrees, and
# reports how the base diverges from origin's default branch so a rebase is no
# surprise. It never modifies any existing checkout.
#
# Usage:
#   worktree-new.sh [--fetch] <branch> [base-ref] [-- <worktree-sync.sh args>...]
#
#   --fetch       `git fetch origin` first (updates origin/* only) so the base
#                 and divergence report reflect the real remote state.
#   <branch>      Branch to create (or check out if it already exists).
#   [base-ref]    Base for a new branch. Default: HEAD.
#   -- ARGS       Everything after -- is passed through to worktree-sync.sh
#                 (e.g. --copy-caches, --no-caches, --dry-run).
#
# Examples:
#   worktree-new.sh feature/login
#   worktree-new.sh --fetch hotfix origin/main
#   worktree-new.sh spike -- --copy-caches
set -Eeuo pipefail

SELF=$(basename "$0")
SELF_DIR=$(cd "$(dirname "$0")" && pwd)
SYNC="$SELF_DIR/worktree-sync.sh"

die()  { printf '%s: %s\n' "$SELF" "$*" >&2; exit 1; }
warn() { printf '%s: %s\n' "$SELF" "$*" >&2; }

FETCH=0
# Leading options (before the positional <branch>).
while [[ ${1:-} == --* && ${1:-} != "--" ]]; do
  case "$1" in
    --fetch) FETCH=1; shift;;
    -h|--help) awk 'NR==1{next} /^set -Eeuo/{exit} {sub(/^# ?/,""); print}' "$0"; exit 0;;
    *) die "unknown option: $1 (try --help)";;
  esac
done

[[ $# -ge 1 ]] || die "usage: $SELF [--fetch] <branch> [base-ref] [-- <sync args>...]"
command -v git >/dev/null 2>&1 || die "git is required"

BRANCH=$1; shift
BASE="HEAD"
SYNC_ARGS=()
if [[ $# -gt 0 && $1 != "--" ]]; then BASE=$1; shift; fi
if [[ ${1:-} == "--" ]]; then shift; SYNC_ARGS=("$@"); fi

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repository"

# Repo root = the main worktree (first entry of `git worktree list`).
# NOTE: the awk below must consume ALL of git's output. Exiting after the
# first match closes the pipe while git is still writing, git dies of
# SIGPIPE, and `set -o pipefail` aborts the whole script with a silent
# exit 141. Racy: ~28% per call in a 35-worktree repo.
ROOT=$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{if(!s){print $2; s=1}}')
[[ -n $ROOT ]] || die "could not determine main worktree"
ROOT=$(cd "$ROOT" && pwd)

# Refresh remote-tracking refs (safe: updates origin/* only) so base/divergence
# reflect reality.
if [[ $FETCH -eq 1 ]]; then
  printf 'fetching origin...\n'
  git -C "$ROOT" fetch --quiet origin || warn "fetch failed; continuing with local refs"
fi

# ---- pre-flight: surface anything that could lose work or cause conflicts ----
# Read-only. Does not modify any checkout.
CUR=$(git rev-parse --show-toplevel 2>/dev/null || echo "$ROOT")
if [[ -n $(git -C "$CUR" status --porcelain 2>/dev/null) ]]; then
  warn "current checkout ($CUR) has uncommitted changes."
  warn "  -> they are SAFE (this never touches that checkout) but will NOT be in"
  warn "     the new worktree. To carry them: commit, or 'git -C \"$CUR\" stash"
  warn "     push -u' then 'git stash apply' in the worktree. Never drop work you"
  warn "     did not create."
fi

printf 'existing worktrees:\n'
git -C "$ROOT" worktree list | sed 's/^/  /'

# Divergence of BASE from the integration branch, so a rebase is no surprise.
DEFREF=$(git -C "$ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)
if [[ -n $DEFREF ]] && git -C "$ROOT" rev-parse --verify -q "$BASE" >/dev/null 2>&1; then
  if counts=$(git -C "$ROOT" rev-list --left-right --count "$BASE...$DEFREF" 2>/dev/null); then
    behind=${counts#*$'\t'}; ahead=${counts%$'\t'*}
    if [[ ${behind:-0} -gt 0 ]]; then
      warn "base '$BASE' is $behind commit(s) behind $DEFREF (ahead $ahead) — expect to rebase/merge before finishing."
      [[ $FETCH -eq 1 ]] || warn "  (run with --fetch first for an accurate picture)"
    fi
  fi
fi
# ------------------------------------------------------------------------------

# Slug: branch name made filesystem-friendly (feature/login -> feature-login).
SLUG=$(printf '%s' "$BRANCH" | tr '/' '-' | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^-*//; s/-*$//')
[[ -n $SLUG ]] || die "could not derive a slug from branch '$BRANCH'"
DEST="$ROOT/.worktrees/$SLUG"

[[ ! -e $DEST ]] || die "worktree path already exists: $DEST"

# Keep .worktrees/ out of git. Prefer the committed .gitignore; otherwise add a
# local-only exclude so the directory never shows up as untracked.
if ! git -C "$ROOT" check-ignore -q .worktrees 2>/dev/null; then
  EXCLUDE="$(git -C "$ROOT" rev-parse --git-common-dir)/info/exclude"
  if [[ -f $EXCLUDE ]] && ! grep -qxF '/.worktrees/' "$EXCLUDE" 2>/dev/null; then
    printf '/.worktrees/\n' >> "$EXCLUDE"
    printf '%s: added /.worktrees/ to %s (consider committing it to .gitignore)\n' "$SELF" "$EXCLUDE" >&2
  fi
fi

mkdir -p "$ROOT/.worktrees"

# Create the worktree: new branch from BASE, or check out an existing branch.
if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  printf 'creating worktree for existing branch %s\n' "$BRANCH"
  git -C "$ROOT" worktree add "$DEST" "$BRANCH"
else
  printf 'creating worktree with new branch %s from %s\n' "$BRANCH" "$BASE"
  git -C "$ROOT" worktree add -b "$BRANCH" "$DEST" "$BASE"
fi

# Sync it warm.
if [[ -x $SYNC ]]; then
  "$SYNC" "$DEST" ${SYNC_ARGS[@]+"${SYNC_ARGS[@]}"}
else
  printf '%s: %s not found/executable — worktree created but NOT synced\n' "$SELF" "$SYNC" >&2
fi

printf '\nworktree ready: %s\n' "$DEST"
printf 'next: cd %q\n' "$DEST"
