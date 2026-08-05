# quick-push

Stage all changes from the repo root, optionally bump the project version, update CHANGELOG, commit with a Claude co-authorship trailer, and push to the current or a new feature branch. Session closeout is handled separately by `wrap-session`.

## What it does

1. **Orient** — read injected git state (branch, dirty files, recent commits).
2. **Bump** version if changes warrant it (skip with `--no-bump`). Update project version files such as `Cargo.toml`, `package.json`, `pyproject.toml`, or README badges only when that repo documents the contract; do not bump plugin manifests by default.
3. **Changelog** — document prior commits under the new version heading.
4. **Preserve boundaries** by leaving personal knowledge-base logging to `wrap-session`.
5. **Stage / commit / push** from the repo root with a meaningful message and Claude trailer.

Never force-pushes. Halts on save failures and hook failures rather than skipping them.

## Invoke

Triggers: "quick push", "push my changes", "commit and push", "ship this", "push to a new branch". Slash-command oriented (`disable-model-invocation: true`).

## Arguments

- `--no-bump` — skip the version bump step

## Files

- `SKILL.md` — the workflow
