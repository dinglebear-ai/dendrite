#!/usr/bin/env bash
# worktree-rm.sh — remove a worktree without losing work.
#
# Removal is where uncommitted/unpushed work actually gets lost. This refuses to
# remove a worktree that has real uncommitted changes or unpushed commits unless
# you pass --force, then removes it cleanly. Synced state (git-ignored secrets,
# config, and symlinked caches) does not count as "work" — only real changes do.
#
# Usage:
#   worktree-rm.sh [options] <worktree | slug | branch>
#
#   <worktree|slug|branch>   Path to a worktree, a .worktrees/<slug> name, or the
#                            branch checked out in the worktree to remove.
#
# Options:
#   --delete-branch   Also delete the branch after removing the worktree
#                     (safe `git branch -d`; with --force, `-D`).
#   --force           Remove even with uncommitted/unpushed work; force branch -D.
#   -n, --dry-run     Show what would happen, change nothing.
#   -h, --help        Show this help.
set -Eeuo pipefail

SELF=$(basename "$0")
die()  { printf '%s: %s\n' "$SELF" "$*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }

# Print the comment header (portable: GNU + BSD/macOS awk).
usage() { awk 'NR==1{next} /^set -Eeuo/{exit} {sub(/^# ?/,""); print}' "$0"; }

DELETE_BRANCH=0
FORCE=0
DRY_RUN=0
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --delete-branch) DELETE_BRANCH=1; shift;;
    --force)         FORCE=1; shift;;
    -n|--dry-run)    DRY_RUN=1; shift;;
    -h|--help)       usage; exit 0;;
    -*)              die "unknown option: $1 (try --help)";;
    *)
      if [[ -z $TARGET ]]; then
        TARGET=$1
      else
        die "unexpected argument: $1"
      fi
      shift
      ;;
  esac
done

[[ -n $TARGET ]] || die "usage: $SELF [options] <worktree | slug | branch>"
command -v git >/dev/null 2>&1 || die "git is required"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repository"

# NOTE: the awk below must consume ALL of git's output. Exiting after the
# first match closes the pipe while git is still writing, git dies of
# SIGPIPE, and `set -o pipefail` aborts the whole script with a silent
# exit 141. Racy: ~28% per call in a 35-worktree repo.
ROOT=$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{if(!s){print $2; s=1}}')
[[ -n $ROOT ]] || die "could not determine main worktree"
ROOT=$(cd "$ROOT" && pwd)

# ---- resolve the target worktree path --------------------------------------
WT=""
if [[ -d $TARGET ]] && git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  WT=$(cd "$TARGET" && git rev-parse --show-toplevel)
elif [[ -d "$ROOT/.worktrees/$TARGET" ]]; then
  WT=$(cd "$ROOT/.worktrees/$TARGET" && pwd)
else
  # treat TARGET as a branch name: find the worktree that has it checked out
  # Same SIGPIPE hazard as above: match without exiting early.
  WT=$(git -C "$ROOT" worktree list --porcelain 2>/dev/null | awk -v b="refs/heads/$TARGET" '
    /^worktree /{p=$2} /^branch /{if ($2==b && !s){print p; s=1}}')
fi
[[ -n $WT && -d $WT ]] || die "could not find a worktree for '$TARGET'"
WT=$(cd "$WT" && pwd)

[[ $WT != "$ROOT" ]] || die "refusing to remove the main worktree ($ROOT)"

BRANCH=$(git -C "$WT" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
printf 'target worktree: %s%s\n' "$WT" "${BRANCH:+  (branch: $BRANCH)}"

# ---- safety: real uncommitted changes? -------------------------------------
# Synced state does not count as work: copied secrets/config are git-ignored (so
# `git status` never reports them), and symlinked caches point back into the main
# checkout. We separate genuine changes from that synced state:
#   - tracked modifications / staged / deletions  -> always real work
#   - untracked entries, minus symlinks into the main checkout -> real work
TRACKED=$(git -C "$WT" status --porcelain --untracked-files=no 2>/dev/null)
UNTRACKED_REAL=""
while IFS= read -r f; do
  [[ -n $f ]] || continue
  full="$WT/${f%/}"
  if [[ -L $full ]]; then
    tgt=$(readlink "$full")
    case "$tgt" in "$ROOT"/*|"$ROOT") continue;; esac   # our synced cache symlink
  fi
  UNTRACKED_REAL+="  ?? $f"$'\n'
done < <(git -C "$WT" ls-files --others --exclude-standard 2>/dev/null)

if [[ -n $TRACKED || -n $UNTRACKED_REAL ]]; then
  echo "uncommitted work in the worktree:" >&2
  [[ -n $TRACKED ]] && printf '%s\n' "$TRACKED" | sed 's/^/    /' >&2
  [[ -n $UNTRACKED_REAL ]] && printf '%s' "$UNTRACKED_REAL" | sed 's/^/  /' >&2
  [[ $FORCE -eq 1 ]] || die "refusing to remove (uncommitted work). Commit/stash, or pass --force."
  note "(--force) proceeding despite uncommitted changes"
fi

# ---- safety: unpushed commits? --------------------------------------------
if [[ -n $BRANCH ]]; then
  if UP=$(git -C "$WT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
    AHEAD=$(git -C "$WT" rev-list --count "@{u}..HEAD" 2>/dev/null || echo 0)
    if [[ ${AHEAD:-0} -gt 0 ]]; then
      echo "branch $BRANCH has $AHEAD commit(s) not pushed to $UP" >&2
      [[ $FORCE -eq 1 ]] || die "refusing to remove (unpushed commits). Push, or pass --force."
      note "(--force) proceeding despite unpushed commits"
    fi
  else
    echo "branch $BRANCH has no upstream — its commits exist only in this worktree" >&2
    [[ $FORCE -eq 1 || $DELETE_BRANCH -eq 0 ]] || die "refusing to delete an unpushed branch without --force."
    [[ $FORCE -eq 1 ]] || note "worktree will be removed but branch $BRANCH kept (no upstream)"
  fi
fi

# ---- remove ----------------------------------------------------------------
# Always --force the git call: synced cache symlinks read as untracked to git
# (a dir-only ignore pattern like `node_modules/` does not match a symlink), so
# a plain remove would refuse. Safety was already enforced above.
if [[ $DRY_RUN -eq 1 ]]; then
  note "git worktree remove --force $WT"
else
  git -C "$ROOT" worktree remove --force "$WT" && note "removed worktree $WT"
fi

# ---- optionally delete the branch -----------------------------------------
if [[ $DELETE_BRANCH -eq 1 && -n $BRANCH ]]; then
  # never delete a branch still checked out elsewhere
  if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -q "refs/heads/$BRANCH"; then
    note "branch $BRANCH is still checked out in another worktree — not deleting"
  else
    local_flag="-d"; [[ $FORCE -eq 1 ]] && local_flag="-D"
    if [[ $DRY_RUN -eq 1 ]]; then
      note "git branch $local_flag $BRANCH"
    else
      if git -C "$ROOT" branch "$local_flag" "$BRANCH"; then
        note "deleted branch $BRANCH"
      else
        note "branch $BRANCH not deleted (unmerged — use --force to force)"
      fi
    fi
  fi
fi

echo "done."
