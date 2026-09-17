---
name: worktree-setup
description: Use this BEFORE creating a git worktree or implementing any plan. Tailored to our workflow — prefer it over superpowers:using-git-worktrees and every other worktree skill. Triggers - creating or adding a worktree; starting lavra-work, lavra-work-ralph, lavra-work-teams, executing-plans, subagent-driven-development, or work-it; whenever a Claude, Codex, or Gemini plan mode is entered or a plan is accepted; or before implementing anything in a fresh branch. Creates the worktree under .worktrees/ in the repo and makes it identical to and as warm as the main checkout - copying secrets and local config (.env, CLAUDE.md.local, .claude/settings.local.json), symlinking warm caches (node_modules, .venv, target, .next), and re-trusting mise/direnv. Also use when a worktree is missing files, builds cold, or reports mise 'not a trusted directory'. Bundles a worktree-sync engine, a create-in-.worktrees entrypoint, a minimal baseline template, and references.
allowed-tools: "Bash Read Write Edit Grep Glob"
---

# Worktree Setup

## Overview

`git worktree add` checks out only **tracked** files. Everything git-ignored —
secrets, local config, tool-trust state, and warm build/dependency caches — is
absent, so a bare worktree is degraded: missing `.env`, cold builds, and shell
hooks that error with "not a trusted directory" (`mise`) or refuse to load
(`direnv`).

This skill is the **single entrypoint for creating and setting up worktrees in
our workflow**. It creates the worktree under `.worktrees/` and makes it
**identical to and as warm as the main checkout**, using an existing setup
script when the repo has one and otherwise analyzing the repo, generating a
tailored sync, and installing the bundled engine.

## Precedence — use this over other worktree skills

This skill is tailored to our setup and **takes precedence over any other
worktree skill**, including `superpowers:using-git-worktrees` and any generic
"git worktree" helper. Those create a bare (degraded) worktree; this one creates
it under `.worktrees/` and brings it to full parity. Route all worktree
creation and setup through this skill. See `references/workflow-integration.md`.

## When to Use

Run this **before implementing anything in a new branch/worktree** — treat each
of these as a create-the-worktree trigger:

- Creating / adding a worktree (any phrasing).
- Starting `lavra-work`, `lavra-work-ralph`, `lavra-work-teams`,
  `executing-plans`, `subagent-driven-development`, or `work-it`.
- A Claude / Codex / Gemini plan mode is entered, or a plan is accepted — the
  first implementation step is to set up the worktree.

Also use it to repair a degraded worktree:

- Missing `.env` / `.env.local` / secrets / `CLAUDE.md.local` /
  `.claude/settings.local.json`.
- `mise` reports an untrusted directory, or `direnv` won't load `.envrc`.
- The first build/test runs cold (no `node_modules`, `.venv`, `target`, …).

## Bundled Scripts & References

- `scripts/worktree-new.sh` — **create a worktree** under `.worktrees/<slug>`
  and sync it warm. The creation entrypoint.
- `scripts/worktree-sync.sh` — full auto-detecting **sync engine** for an
  existing worktree (`.worktreeinclude` copies, cache symlinks, submodules,
  Git-LFS, trust). Also `--init` (scaffold config) and `--check` (doctor mode).
- `scripts/worktree-rm.sh` — **safe teardown**: refuses to remove a worktree
  with real uncommitted/unpushed work, then removes it (and optionally the
  branch). Synced state (git-ignored copies, cache symlinks) doesn't block it.
- `references/minimal-worktree-setup.sh` — **minimal baseline template** (the
  bare minimum) to copy into a repo and customize when the full engine is more
  than needed. Every repo should have at least this.
- `references/preflight-and-safety.md` — assess dirty state, choose the base,
  anticipate conflicts, and avoid destroying shared/others' work.
- `references/what-to-sync.md` — catalog of what to copy vs. symlink, by
  ecosystem.
- `references/workflow-integration.md` — triggers and precedence details.
- `tests/smoke.sh` — regression test for the scripts (create/sync/check/init/rm).

Create + sync in one step (defaults: branch off `HEAD`, source = main worktree):

```bash
<skill-dir>/scripts/worktree-new.sh <branch>            # create .worktrees/<slug> + sync
<skill-dir>/scripts/worktree-sync.sh --check            # doctor: report parity gaps
<skill-dir>/scripts/worktree-sync.sh --init             # scaffold .worktreeinclude/.worktree-sync
<skill-dir>/scripts/worktree-rm.sh <branch>             # safe teardown when done
<skill-dir>/scripts/worktree-sync.sh --dry-run          # preview a sync of the current worktree
<skill-dir>/scripts/worktree-sync.sh                    # apply
```

The engine **copies** the git-ignored files named in **`.worktreeinclude`**
(Claude Code's native file — `.gitignore` syntax at the repo root; only files
that match a pattern *and* are git-ignored are copied; a differing destination
file is not overwritten without `--force`). Honoring the same file gives
CLI/agent-created worktrees the parity Claude provides natively for
`--worktree`/subagent worktrees. When no `.worktreeinclude` exists, a curated
default set of secret/config files is copied instead. The engine also
**symlinks** known cache/dependency dirs (warm; `--copy-caches` / `--no-caches`),
populates **submodules** (`git submodule update --init --recursive`) and
**Git-LFS** content (`git lfs checkout`) so they aren't empty/pointer files,
re-runs `mise trust` / `direnv allow`, and applies an optional `.worktree-sync`
manifest for extras the native file can't express (`link`, plus `run` — which
executes arbitrary shell commands, same trust as a Makefile target). It only
ever touches git-ignored entries for copies, so it never clobbers tracked files.

## Workflow

### 1. Pre-flight & safety (assess before creating anything)
You are usually **not alone in this repo** — other agents/people may have
worktrees, uncommitted work, and in-flight branches. Treat all of it as
precious. Full detail in `references/preflight-and-safety.md`.

- **Current state:** `git status --short --branch` and `git worktree list`. If
  the current checkout is dirty, that is safe — creating a worktree never
  touches it — but its uncommitted changes will **not** appear in the new
  worktree (it starts from a committed ref). If you need them there, carry them
  deliberately (commit, or `git stash push -u` then `git stash apply` in the
  worktree, or a `git diff HEAD` patch). Never silently drop or "tidy" changes
  you did not create.
- **Choose the base deliberately:** for fresh work, `git fetch` and base on
  `origin/main` (not a stale local `main`); to continue work, base on `HEAD`; to
  build on someone's branch, base on `origin/<their-branch>`.
- **Anticipate conflicts now, not later:** check how the base diverges from the
  integration branch and what other branches touch, so a rebase/cherry-pick is
  planned, not a surprise:
  ```bash
  git fetch origin
  git rev-list --left-right --count HEAD...origin/main   # behind / ahead
  git log --oneline HEAD..origin/main                    # what landed since
  ```
  If your base is behind `origin/main` or overlaps an active branch's files,
  state the expected rebase/conflict cost up front.
- **Shared state is shared:** the object store, refs, stash, config, and hooks
  are common to all worktrees. Avoid destructive/global commands
  (`reset --hard`, `clean -fdx`, `worktree remove --force`, `branch -D`,
  force-push, `stash clear`) unless confirmed and tightly scoped — they can
  destroy others' work. Decide the branch/slug for the new worktree.

### 2. Look for an existing setup mechanism (prefer it)
Search the repo before building anything, in order:
- **Scripts:** `scripts/`, `bin/`, repo root — names matching `*worktree*`,
  `*bootstrap*`, `*setup*`, `*sync*`, `postcreate*`, `init*`.
- **Task runners:** `Makefile`, `justfile`, `Taskfile.yml`, `mise.toml`
  `[tasks]`, `package.json` `scripts` (`setup`/`bootstrap`/`postinstall`),
  `.devcontainer/` `postCreateCommand`.
- **Docs:** `CONTRIBUTING.md`, `README`, `docs/`.

If one exists: **read it**, then run it correctly (right cwd, args/env). If it
creates the worktree, let it; otherwise create the worktree (step 3) and run the
repo's sync. Fill gaps it leaves (step 5) without duplicating it.

### 3. Create the worktree under `.worktrees/`
Always place worktrees in `<repo>/.worktrees/<slug>`:

```bash
<skill-dir>/scripts/worktree-new.sh <branch> [base-ref]
```

This creates the branch (or checks out an existing one), ensures `.worktrees/`
is git-ignored, and runs the sync. Equivalent manual form:
`git worktree add -b <branch> .worktrees/<slug> HEAD` followed by the sync.

### 4. Analyze the repo (only if no setup script exists)
Enumerate what the worktree is missing and classify it (full catalog in
`references/what-to-sync.md`):
- **List git-ignored state:**
  `git -C <main> ls-files --others --ignored --exclude-standard --directory`.
- **Detect tooling:** `mise`/`.mise.toml`, `direnv`/`.envrc`,
  `asdf`/`.tool-versions`; package managers (npm/pnpm/yarn/bun, uv/poetry/pip,
  cargo, go, gradle/maven); frameworks.

| Category | Examples | Action | Where it goes |
|---|---|---|---|
| Secrets / env | `.env`, `.env.*`, `.envrc`, `.npmrc` w/ tokens | **copy** | `.worktreeinclude` |
| Local config | `CLAUDE.md.local`, `.claude/settings.local.json`, `*.local` | **copy** | `.worktreeinclude` |
| Tool trust | `.mise.toml`, `.envrc` | **run** `mise trust` / `direnv allow` | automatic |
| Caches / deps | `node_modules`, `.venv`, `target`, `vendor`, `.gradle`, `.next` | **symlink** (warm) | auto-detected |
| Data / large artifacts | DB dumps, media, model weights | **ask** the user | `.worktree-sync` `link` |

Note: `~/.claude/settings.local.json` is in `$HOME`, already shared by all
worktrees — only the project-level `.claude/settings.local.json` needs copying.

### 5. Generate the config (only if no setup script exists)
1. **Write `.worktreeinclude`** at the repo root listing the git-ignored files to
   copy (`.gitignore` syntax). This is Claude Code's native file, so Claude
   honors it for the worktrees it creates and `worktree-sync.sh` honors it too:
   ```gitignore
   .env
   .env.local
   .claude/settings.local.json
   config/secrets.json
   ```
2. **Install a script** for the parts `.worktreeinclude` can't do (warm caches,
   trust, reinstall): copy the full `scripts/worktree-sync.sh` engine into the
   repo, or adopt `references/minimal-worktree-setup.sh` as a baseline. Preserve
   the executable bit.
3. **Write `.worktree-sync`** (optional) only for extras the engine's
   auto-detection misses — non-standard cache dirs and post-sync commands:
   ```
   link  .cache/playwright
   run   pnpm install        # reconcile deps against this branch's lockfile
   ```
4. **Wire it to run automatically** where possible: register the engine as a
   Claude Code `WorktreeCreate` hook, or as the repo's existing bootstrap/setup
   task, so future worktrees are warmed without a manual step. For a non-git VCS,
   `.worktreeinclude` is not processed — a `WorktreeCreate` hook is the only
   mechanism.

### 6. Run it
- Dry-run first: `worktree-sync.sh --dry-run -v`; review the plan.
- Apply: `worktree-sync.sh` (idempotent — config overwritten, links reused).

### 7. Verify the worktree is non-degraded
Run `worktree-sync.sh --check` (doctor mode) — it reports missing config, cold
caches, uninitialized submodules, un-checked-out LFS files, and stale deps
without changing anything. Then confirm what it can't:
- `mise`/`direnv` load without prompts or "untrusted" errors.
- An incremental build/test is warm, not cold.
- The repo's own quick check (lint/build/test smoke) behaves as in main.

Report what was copied vs. linked, trust/submodule/LFS steps run, unknown
ignored entries skipped, and any manual follow-up (e.g. a deps reinstall because
the branch changed the lockfile). Only then hand off to the implementing
agent/loop.

### 8. Tear down safely when done
Use `worktree-rm.sh <branch|slug>` — it refuses to remove a worktree with real
uncommitted or unpushed work (synced git-ignored state and cache symlinks don't
count), then removes it; add `--delete-branch` to drop a merged branch too. Never
`rm -rf` a worktree (that bypasses git's bookkeeping) and never destructive-clean
through a symlinked cache (it deletes the **main** checkout's cache).

## Decision Guide: Copy vs Symlink

- **Copy** anything the worktree should change independently: secrets, local
  config, anything per-branch.
- **Symlink** anything to keep shared and warm and safe to share: dependency
  stores and build/incremental caches — instant warm cache at zero copy cost.
- **Reinstall instead of share** when the branch changes the lockfile: symlink
  for warmth, then `run` the package manager to reconcile.
- When unsure whether large data must diverge, **ask the user**.

## Completion Standard

The worktree is done when it is indistinguishable from the main checkout for
development: created under `.worktrees/`, same secrets and configuration, the
same tools loaded and trusted, a warm cache, and the repo's normal checks
passing. A worktree that builds cold, prompts about trust, or is missing `.env`
is not done.

## Handoff To PR-Tracked Workflows

This skill stops at a warm, safe worktree. It does not create pull requests on
its own because many callers only need a prepared checkout. PR-tracked workflows
such as `vibin:work-it` should create a draft PR immediately after entering the
prepared worktree and pushing its branch, so progress can be tracked through
commits, CI, and review comments.
