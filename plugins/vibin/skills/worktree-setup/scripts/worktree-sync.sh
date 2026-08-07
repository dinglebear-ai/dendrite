#!/usr/bin/env bash
# worktree-sync.sh — give a git worktree the same warm, fully-configured
# experience as the main checkout.
#
# A fresh `git worktree add` only materializes *tracked* files. Everything that
# makes a checkout usable but is git-ignored — secrets (.env), local config
# (CLAUDE.md.local, .claude/settings.local.json), tool-trust state (.mise.toml),
# and warm build/dependency caches (node_modules, .venv, target, .next) — is
# missing, and submodules/Git-LFS content may be absent too. This script brings
# that state across so the new worktree is non-degraded from the first command.
#
# Strategy:
#   - COPY  secrets and local config  → each worktree gets its own copy so it
#                                        can diverge safely.
#   - LINK  caches and dependency dirs → shared with the main checkout for an
#                                        instantly warm build (use --copy-caches
#                                        to duplicate instead).
#   - INIT  submodules + Git-LFS       → populate submodule trees and LFS content
#                                        so they are not empty/pointer files.
#   - TRUST re-run `mise trust` / `direnv allow` so shell hooks load silently.
#
# What to copy is driven by `.worktreeinclude` (Claude Code's native file) when
# present: .gitignore-syntax patterns, and only files that match AND are
# git-ignored are copied (tracked files are never duplicated). This honors the
# same file Claude uses for `--worktree`/subagent worktrees, giving CLI/agent
# parity. Without a `.worktreeinclude`, a curated default set of secret/config
# files is copied instead. An existing destination file is not overwritten
# unless its contents differ and --force is given.
#
# Symlinked warm caches are auto-detected (zero config). Anything the native
# file can't express — extra symlinks, post-sync commands — lives in an optional
# `.worktree-sync` manifest at the repo root (see below).
#
# Usage:
#   worktree-sync.sh [options] [DEST]   # sync DEST (default: current worktree)
#   worktree-sync.sh --check [DEST]     # report parity gaps, change nothing
#   worktree-sync.sh --init             # scaffold .worktreeinclude/.worktree-sync
#
# Options:
#   --from PATH         Source checkout to sync from. Default: the main worktree.
#   --include PATH      .worktreeinclude file. Default: <source>/.worktreeinclude.
#   --manifest PATH     Manifest file. Default: <source>/.worktree-sync.
#   --force             Overwrite destination files that differ from the source.
#   --copy-caches       Copy cache/dependency dirs instead of symlinking them.
#   --no-caches         Skip cache/dependency dirs entirely.
#   --no-submodules     Skip `git submodule update --init --recursive`.
#   --no-lfs            Skip `git lfs checkout`.
#   --no-trust          Skip `mise trust` / `direnv allow`.
#   --check             Doctor mode: report gaps (missing config, cold cache,
#                       uninit submodules, LFS pointers, stale deps); exit 1 if any.
#   --init              Write starter .worktreeinclude + .worktree-sync, then exit.
#   -n, --dry-run       Print actions without changing anything.
#   -v, --verbose       Explain skipped candidates too.
#   -h, --help          Show this help.
#
# .worktreeinclude format (.gitignore syntax), at the source root:
#   .env
#   .env.local
#   .claude/settings.local.json
#
# .worktree-sync manifest (lines, # for comments). Paths relative to source root:
#   link  relative/path        # symlink a cache/dir the auto-detector misses
#   run   shell command         # run after sync, cwd = worktree root
#   copy  relative/path        # copy a file/dir (.worktreeinclude is preferred)
# NOTE: `run` executes arbitrary shell commands (same trust as a Makefile target).
set -Eeuo pipefail

SELF=$(basename "$0")

# ---- option parsing --------------------------------------------------------
SOURCE=""
DEST=""
INCLUDE=""
MANIFEST=""
CACHE_MODE="link"   # link | copy | skip
DO_SUBMODULES=1
DO_LFS=1
DO_TRUST=1
DRY_RUN=0
VERBOSE=0
FORCE=0
INIT=0
CHECK=0

die()  { printf '%s: %s\n' "$SELF" "$*" >&2; exit 1; }
note() { printf '  %s\n' "$*"; }
info() { printf '  - %s\n' "$*"; }
vnote(){ [[ $VERBOSE -eq 1 ]] && printf '  (skip) %s\n' "$*" || true; }

# Print the comment header (portable: GNU + BSD/macOS awk).
usage() { awk 'NR==1{next} /^set -Eeuo/{exit} {sub(/^# ?/,""); print}' "$0"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)         SOURCE=${2:?--from needs a path}; shift 2;;
    --include)      INCLUDE=${2:?--include needs a path}; shift 2;;
    --manifest)     MANIFEST=${2:?--manifest needs a path}; shift 2;;
    --force)        FORCE=1; shift;;
    --copy-caches)  CACHE_MODE="copy"; shift;;
    --no-caches)    CACHE_MODE="skip"; shift;;
    --no-submodules) DO_SUBMODULES=0; shift;;
    --no-lfs)       DO_LFS=0; shift;;
    --no-trust)     DO_TRUST=0; shift;;
    --check)        CHECK=1; shift;;
    --init)         INIT=1; shift;;
    -n|--dry-run)   DRY_RUN=1; shift;;
    -v|--verbose)   VERBOSE=1; shift;;
    -h|--help)      usage; exit 0;;
    -*)             die "unknown option: $1 (try --help)";;
    *)
      if [[ -z $DEST ]]; then
        DEST=$1
      else
        die "unexpected argument: $1"
      fi
      shift
      ;;
  esac
done

command -v git >/dev/null 2>&1 || die "git is required"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repository"

# NOTE: the awk below must consume ALL of git's output. Exiting after the
# first match closes the pipe while git is still writing, git dies of
# SIGPIPE, and `set -o pipefail` aborts the whole script with a silent
# exit 141. Racy: ~28% per call in a 35-worktree repo.
main_worktree() { git worktree list --porcelain 2>/dev/null | awk '/^worktree /{if(!s){print $2; s=1}}'; }

# ---- classifiers (portable: no associative arrays, bash 3.2-safe) ----------
safe_relative_path() {
  local p=$1
  [[ -n $p && $p != /* ]] || return 1
  case "/$p/" in
    */../*|*/./*) return 1;;
  esac
  return 0
}

ignored_source_path() {
  local p=$1
  git -C "$SOURCE" check-ignore -q -- "$p"
}

# basename patterns that identify copy-worthy secret / local-config files
is_config_file() {
  case "$1" in
    *.md.example|*.example|*.sample|*.template|*.dist) return 1;;
  esac
  case "$1" in
    .env|.env.*|.envrc|.npmrc|.yarnrc|.yarnrc.yml|.netrc|.pgpass) return 0;;
    *.local|*.local.*) return 0;;            # CLAUDE.md.local, config.local.toml, settings.local.json
    secrets|secrets.*|.secrets|.secrets.*) return 0;;
  esac
  return 1
}

# directory basenames treated as warm caches / dependency stores
is_cache_dir() {
  case "$1" in
    node_modules|.pnpm-store|.yarn|bower_components) return 0;;
    .venv|venv|.tox|.nox|__pypackages__) return 0;;
    target|vendor|.gradle|.m2|build|out|dist) return 0;;
    .next|.nuxt|.svelte-kit|.turbo|.vite|.parcel-cache|.angular|.astro) return 0;;
    .cache|.pytest_cache|.mypy_cache|.ruff_cache|.terraform|.dart_tool) return 0;;
    *) return 1;;
  esac
}

# suggested dependency reinstall, based on lockfiles present in $SOURCE
suggest_reinstall() {
  [[ -f "$SOURCE/pnpm-lock.yaml" ]]    && { echo "pnpm install"; return; }
  [[ -f "$SOURCE/yarn.lock" ]]         && { echo "yarn install"; return; }
  [[ -f "$SOURCE/bun.lockb" ]]         && { echo "bun install"; return; }
  [[ -f "$SOURCE/package-lock.json" ]] && { echo "npm ci"; return; }
  [[ -f "$SOURCE/uv.lock" ]]           && { echo "uv sync"; return; }
  [[ -f "$SOURCE/poetry.lock" ]]       && { echo "poetry install"; return; }
  [[ -f "$SOURCE/requirements.txt" ]]  && { echo "pip install -r requirements.txt"; return; }
  [[ -f "$SOURCE/Cargo.toml" ]]        && { echo "cargo fetch"; return; }
  [[ -f "$SOURCE/go.mod" ]]            && { echo "go mod download"; return; }
  [[ -f "$SOURCE/Gemfile.lock" ]]      && { echo "bundle install"; return; }
  return 0
}

# ============================================================================
# INIT mode — scaffold config files, then exit. Needs SOURCE only.
# ============================================================================
if [[ $INIT -eq 1 ]]; then
  [[ -n $SOURCE ]] || SOURCE=$(main_worktree)
  [[ -n $SOURCE && -d $SOURCE ]] || die "could not determine source checkout; pass --from"
  SOURCE=$(cd "$SOURCE" && pwd)
  [[ -z $INCLUDE ]]  && INCLUDE="$SOURCE/.worktreeinclude"
  [[ -z $MANIFEST ]] && MANIFEST="$SOURCE/.worktree-sync"

  echo "scaffolding worktree config in $SOURCE"
  if [[ -e $INCLUDE ]]; then
    note ".worktreeinclude exists — left unchanged"
  else
    {
      echo "# .worktreeinclude — git-ignored files to copy into new worktrees."
      echo "# .gitignore syntax; only files that are ALSO git-ignored are copied."
      echo "# Read natively by Claude Code and by worktree-sync.sh."
      while IFS= read -r rel; do
        rel=${rel%/}
        if [[ -f "$SOURCE/$rel" ]] && is_config_file "$(basename "$rel")"; then echo "$rel"; fi
      done < <(git -C "$SOURCE" ls-files --others --ignored --exclude-standard --directory 2>/dev/null)
    } > "$INCLUDE"
    note "wrote $INCLUDE"
  fi

  if [[ -e $MANIFEST ]]; then
    note ".worktree-sync exists — left unchanged"
  else
    {
      echo "# .worktree-sync — extras .worktreeinclude can't express."
      echo "#   link <path>   symlink an extra cache the auto-detector misses"
      echo "#   run  <cmd>    run after sync (cwd = worktree root)"
      echo "# NOTE: 'run' executes arbitrary shell commands (same trust as a Makefile)."
      echo "#"
      rec=$(suggest_reinstall)
      [[ -n $rec ]] && echo "# run   $rec        # reconcile deps with this branch's lockfile"
      while IFS= read -r rel; do
        rel=${rel%/}
        [[ -d "$SOURCE/$rel" && ! -L "$SOURCE/$rel" ]] || continue
        is_cache_dir "$(basename "$rel")" && continue   # already auto-detected
        echo "# link  $rel"
      done < <(git -C "$SOURCE" ls-files --others --ignored --exclude-standard --directory 2>/dev/null)
    } > "$MANIFEST"
    note "wrote $MANIFEST (review the commented suggestions)"
  fi
  echo "done. review the files, then run 'worktree-sync.sh' inside a worktree."
  exit 0
fi

# ============================================================================
# Resolve source (main worktree) and dest (target worktree) for sync/check.
# ============================================================================
if [[ -z $DEST ]]; then
  DEST=$(git rev-parse --show-toplevel 2>/dev/null) \
    || die "not inside a git worktree; pass DEST explicitly"
fi
[[ -d $DEST ]] || die "destination does not exist: $DEST"
DEST=$(cd "$DEST" && pwd)

if [[ -z $SOURCE ]]; then
  SOURCE=$(git -C "$DEST" worktree list --porcelain 2>/dev/null | awk '/^worktree /{if(!s){print $2; s=1}}')
  [[ -n $SOURCE ]] || die "could not determine main worktree; pass --from"
fi
[[ -d $SOURCE ]] || die "source does not exist: $SOURCE"
SOURCE=$(cd "$SOURCE" && pwd)
[[ $SOURCE != "$DEST" ]] || die "source and destination are the same checkout ($SOURCE)"

[[ -z $INCLUDE ]]  && INCLUDE="$SOURCE/.worktreeinclude"
[[ -z $MANIFEST ]] && MANIFEST="$SOURCE/.worktree-sync"

# ============================================================================
# CHECK mode — report parity gaps without changing anything. Exit 1 if any.
# ============================================================================
if [[ $CHECK -eq 1 ]]; then
  gaps=0
  echo "checking worktree parity: $DEST  (vs $SOURCE)"

  # missing copied config
  if [[ -f $INCLUDE ]]; then
    while IFS= read -r rel; do
      [[ -n $rel && -e "$SOURCE/$rel" ]] || continue
      git -C "$SOURCE" check-ignore -q -- "$rel" || continue
      [[ -e "$DEST/$rel" ]] || { echo "  MISSING config: $rel"; gaps=$((gaps+1)); }
    done < <(git -C "$SOURCE" ls-files --others --ignored --exclude-from="$INCLUDE" 2>/dev/null)
  else
    while IFS= read -r rel; do
      rel=${rel%/}
      if ! [[ -f "$SOURCE/$rel" ]] || ! is_config_file "$(basename "$rel")"; then
        continue
      fi
      [[ -e "$DEST/$rel" ]] || { echo "  MISSING config: $rel"; gaps=$((gaps+1)); }
    done < <(git -C "$SOURCE" ls-files --others --ignored --exclude-standard --directory 2>/dev/null)
  fi

  # cold caches
  while IFS= read -r rel; do
    rel=${rel%/}
    [[ -d "$SOURCE/$rel" && ! -L "$SOURCE/$rel" ]] || continue
    is_cache_dir "$(basename "$rel")" || continue
    [[ -e "$DEST/$rel" ]] || { echo "  COLD cache: $rel"; gaps=$((gaps+1)); }
  done < <(git -C "$SOURCE" ls-files --others --ignored --exclude-standard --directory 2>/dev/null)

  # uninitialized submodules
  if [[ -f "$DEST/.gitmodules" ]]; then
    while IFS= read -r sm; do
      [[ -n $sm ]] || continue
      [[ -e "$DEST/$sm/.git" ]] || { echo "  UNINIT submodule: $sm"; gaps=$((gaps+1)); }
    done < <(git -C "$DEST" config -f .gitmodules --get-regexp 'submodule\..*\.path' 2>/dev/null | awk '{print $2}')
  fi

  # LFS pointers not checked out ('-' marker in `git lfs ls-files`)
  if command -v git-lfs >/dev/null 2>&1; then
    notdl=$(git -C "$DEST" lfs ls-files 2>/dev/null | grep -c -- ' - ' || true)
    [[ ${notdl:-0} -gt 0 ]] && { echo "  LFS pointers not checked out: $notdl file(s)"; gaps=$((gaps+1)); }
  fi

  # stale deps: lockfile differs from main (which the symlinked cache reflects)
  for lf in package-lock.json pnpm-lock.yaml yarn.lock bun.lockb Cargo.lock go.sum poetry.lock uv.lock Gemfile.lock; do
    if [[ -f "$DEST/$lf" && -f "$SOURCE/$lf" ]] && ! cmp -s "$DEST/$lf" "$SOURCE/$lf"; then
      echo "  STALE deps: $lf differs from main — reinstall in the worktree"; gaps=$((gaps+1))
    fi
  done

  # trust reminders (best-effort, informational — do not affect exit code)
  if command -v mise >/dev/null 2>&1 && { [[ -f "$DEST/.mise.toml" || -f "$DEST/mise.toml" ]]; }; then
    ( cd "$DEST" && mise ls >/dev/null 2>&1 ) || info "mise may be untrusted here (run: mise trust)"
  fi
  if command -v direnv >/dev/null 2>&1 && [[ -f "$DEST/.envrc" ]]; then
    ( cd "$DEST" && direnv export bash >/dev/null 2>&1 ) || info "direnv .envrc not allowed (run: direnv allow)"
  fi

  if [[ $gaps -eq 0 ]]; then echo "  OK: no parity gaps found"; exit 0; fi
  echo "  $gaps gap(s) found — run worktree-sync.sh to fix"
  exit 1
fi

# ============================================================================
# SYNC mode
# ============================================================================
printf '%s\n' "worktree-sync: $SOURCE -> $DEST"
[[ $DRY_RUN -eq 1 ]] && printf '%s\n' "(dry run — no changes will be made)"

RSYNC=$(command -v rsync || true)

do_copy() {  # src dest [trailing-slash-for-dir]
  local s=$1 d=$2
  # Native .worktreeinclude rule: do not overwrite a differing destination file
  # unless --force. (Dir copies, signalled by $3, skip this check.)
  if [[ -f $s && -e $d && -z ${3:-} ]]; then
    if cmp -s "$s" "$d"; then vnote "copy  $rel (identical)"; return; fi
    if [[ $FORCE -ne 1 ]]; then note "copy  $rel (exists & differs — use --force)"; return; fi
  fi
  [[ $DRY_RUN -eq 1 ]] && { note "copy  $rel"; return; }
  mkdir -p "$(dirname "$d")"
  if [[ -n $RSYNC ]]; then
    rsync -a --delete "$s${3:-}" "$d"
  else
    rm -rf "$d"; cp -a "$s" "$d"
  fi
  note "copy  $rel"
}

do_link() {  # src dest
  local s=$1 d=$2
  if [[ -L $d && $(readlink "$d") == "$s" ]]; then vnote "link  $rel (already linked)"; return; fi
  [[ $DRY_RUN -eq 1 ]] && { note "link  $rel -> $s"; return; }
  mkdir -p "$(dirname "$d")"
  rm -rf "$d"
  ln -s "$s" "$d"
  note "link  $rel -> $s"
}

# ---- 1a. copy files named by .worktreeinclude (Claude Code's native file) --
HAVE_INCLUDE=0
if [[ -f $INCLUDE ]]; then
  HAVE_INCLUDE=1
  echo "applying .worktreeinclude: $INCLUDE"
  while IFS= read -r rel; do
    [[ -n $rel && -e "$SOURCE/$rel" ]] || continue
    git -C "$SOURCE" check-ignore -q -- "$rel" || { vnote "file  $rel (matched but not git-ignored — skipped)"; continue; }
    do_copy "$SOURCE/$rel" "$DEST/$rel"
  done < <(git -C "$SOURCE" ls-files --others --ignored --exclude-from="$INCLUDE" 2>/dev/null)
else
  vnote "no .worktreeinclude at $INCLUDE (using curated config defaults)"
fi

# ---- 1b. scan git-ignored entries for warm caches (and config fallback) ----
echo "scanning git-ignored entries..."
while IFS= read -r rel; do
  [[ -z $rel ]] && continue
  rel=${rel%/}
  src="$SOURCE/$rel"
  dst="$DEST/$rel"
  base=$(basename "$rel")
  if [[ -d $src && ! -L $src ]]; then
    if is_cache_dir "$base"; then
      case "$CACHE_MODE" in
        link) do_link "$src" "$dst";;
        copy) do_copy "$src" "$dst" "/";;
        skip) vnote "cache $rel (--no-caches)";;
      esac
    else
      vnote "dir   $rel (not a known cache; add to .worktree-sync if needed)"
    fi
  elif [[ -f $src ]]; then
    if [[ $HAVE_INCLUDE -eq 0 ]] && is_config_file "$base"; then
      do_copy "$src" "$dst"
    elif [[ $HAVE_INCLUDE -eq 1 ]]; then
      vnote "file  $rel (copies governed by .worktreeinclude)"
    else
      vnote "file  $rel (not a known config file)"
    fi
  fi
done < <(git -C "$SOURCE" ls-files --others --ignored --exclude-standard --directory 2>/dev/null)

# ---- 2. apply manifest -----------------------------------------------------
RUN_CMDS=()
if [[ -f $MANIFEST ]]; then
  echo "applying manifest: $MANIFEST"
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%%#*}
    line=$(printf '%s' "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    [[ -z $line ]] && continue
    verb=${line%% *}
    arg=${line#* }
    case "$verb" in
      copy)
        rel=$arg
        safe_relative_path "$arg" || die "manifest: '$arg' must be a relative path inside the repo"
        if [[ -e "$SOURCE/$arg" ]]; then
          ignored_source_path "$arg" || die "manifest: refusing to copy tracked/non-ignored path '$arg'"
          do_copy "$SOURCE/$arg" "$DEST/$arg"
        else
          vnote "copy  $arg (missing in source)"
        fi
        ;;
      link)
        rel=$arg
        safe_relative_path "$arg" || die "manifest: '$arg' must be a relative path inside the repo"
        if [[ -e "$SOURCE/$arg" ]]; then
          ignored_source_path "$arg" || die "manifest: refusing to link tracked/non-ignored path '$arg'"
          do_link "$SOURCE/$arg" "$DEST/$arg"
        else
          vnote "link  $arg (missing in source)"
        fi
        ;;
      run)  RUN_CMDS+=("$arg");;
      *)    die "manifest: unknown verb '$verb' (use copy|link|run)";;
    esac
  done < "$MANIFEST"
else
  vnote "no manifest at $MANIFEST"
fi

# ---- 3. submodules ---------------------------------------------------------
if [[ $DO_SUBMODULES -eq 1 && -f "$DEST/.gitmodules" ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then note "submodule update --init --recursive"; else
    note "submodule update --init --recursive"
    ( cd "$DEST" && git submodule update --init --recursive ) \
      || note "submodule update failed — run 'git submodule update --init --recursive' manually"
  fi
fi

# ---- 4. Git LFS ------------------------------------------------------------
if [[ $DO_LFS -eq 1 ]] && command -v git-lfs >/dev/null 2>&1; then
  # The `| head -1` below is the same early-close shape that caused the SIGPIPE
  # aborts above, but it is safe HERE and only here: a command substitution
  # inside `[[ ]]` does not propagate its status, so pipefail cannot abort on it.
  # If this is ever refactored into a plain assignment (`x=$(... | head -1)`),
  # it becomes a crash — drop the `head` at that point.
  if [[ -n $(git -C "$DEST" lfs ls-files 2>/dev/null | head -1) ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then note "git lfs checkout"; else
      note "git lfs checkout"
      ( cd "$DEST" && git lfs checkout ) \
        || note "lfs checkout failed — try 'git lfs pull' (needs network)"
    fi
  fi
fi

# ---- 5. trust shell tooling so hooks load without prompts ------------------
if [[ $DO_TRUST -eq 1 ]]; then
  if command -v mise >/dev/null 2>&1 \
     && { [[ -f "$DEST/.mise.toml" ]] || [[ -f "$DEST/mise.toml" ]] || [[ -f "$DEST/.config/mise/config.toml" ]]; }; then
    if [[ $DRY_RUN -eq 1 ]]; then note "trust mise ($DEST)"; else
      if ( cd "$DEST" && mise trust >/dev/null 2>&1 ); then
        note "trust mise"
      else
        note "trust mise (failed — run 'mise trust' manually)"
      fi
    fi
  fi
  if command -v direnv >/dev/null 2>&1 && [[ -f "$DEST/.envrc" ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then note "trust direnv ($DEST)"; else
      if ( cd "$DEST" && direnv allow >/dev/null 2>&1 ); then
        note "trust direnv"
      else
        note "trust direnv (failed — run 'direnv allow' manually)"
      fi
    fi
  fi
fi

# ---- 6. manifest run hooks (after everything is in place) ------------------
for cmd in ${RUN_CMDS[@]+"${RUN_CMDS[@]}"}; do
  [[ -z $cmd ]] && continue
  if [[ $DRY_RUN -eq 1 ]]; then note "run   $cmd"; else
    note "run   $cmd"
    ( cd "$DEST" && eval "$cmd" )
  fi
done

echo "done."
