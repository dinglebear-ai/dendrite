---
name: log-code-session
description: Create a factual, append-only coding-session log that records repository work, implementation choices, files changed, tests, CI, failures, verification, and follow-ups. Use when the user says "log this coding session", "save the code session", "document the development work", or when wrap-session routes a session containing code, repository, build, test, CI, PR, or release work. This skill writes the log only. It never commits, pushes, opens PRs, changes tracker state, or cleans branches and worktrees.
allowed-tools: Read, Write, Bash
---

## Context

- Date: !`TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z'`
- Working directory: !`pwd`
- Repo root: !`git rev-parse --show-toplevel 2>/dev/null || true`
- Repo remote: !`git remote get-url origin 2>/dev/null || true`
- Branch: !`git branch --show-current 2>/dev/null || true`
- HEAD: !`git rev-parse --short HEAD 2>/dev/null || true`
- Recent commits: !`git log --oneline -10 2>/dev/null || true`
- Dirty files: !`git status --short 2>/dev/null || true`
- Worktrees: !`git worktree list --porcelain 2>/dev/null || true`
- Active PR: !`gh pr view --json number,title,url 2>/dev/null || true`
- Transcript: !`ls -t ~/.claude/projects/$(pwd | sed 's|/|-|g')/*.jsonl 2>/dev/null | head -1`
- Active plan: !`cat .claude/current-plan 2>/dev/null || true`
- Knowledge root: !`if [ -d "${HOMELAB_DOCS_ROOT:-$HOME/docs}/sessions" ]; then printf '%s' "${HOMELAB_DOCS_ROOT:-$HOME/docs}"; fi`

# Log Code Session

Create an accurate coding-session record. The artifact is a curated engineering log, not a raw transcript and not a repository closeout workflow.

## Strict boundary

This skill may read evidence and write one session artifact. It must not:

- stage, commit, push, merge, tag, or open a pull request;
- create, close, assign, or edit tracker issues;
- move plans or rewrite unrelated documentation;
- delete branches, worktrees, files, or temporary state;
- perform implementation work that was not already part of the session.

Record observed tracker, branch, PR, and cleanup activity when relevant, but do not mutate any of it.

## Resolve the output path

1. When the caller supplies a path, use it. Resolve relative paths from the current repository root when one exists, otherwise from the working directory.
2. With no supplied path, prefer `${HOMELAB_DOCS_ROOT:-$HOME/docs}/sessions/YYYY-MM-DD-short-topic.md` when that directory exists.
3. Otherwise use `<repo-root>/docs/sessions/YYYY-MM-DD-short-topic.md`.
4. Create the parent directory only when it does not exist.
5. Never overwrite an existing log. Add `-v2`, `-v3`, and so on.
6. Markdown is the only output format. Rendering is a separate concern.

## Recover the session

Read the injected transcript when available and needed to recover earlier context. Use the current conversation, command results, git evidence, CI output, and referenced files as the factual basis. The transcript path is provenance only. Do not copy the transcript into the artifact.

For a fleet-wide session, inspect each repository actually changed. Do not force a multi-repository session into one misleading repo, branch, or HEAD value.

## Frontmatter

Use flat YAML frontmatter so the current knowledge-base tooling can parse it:

```yaml
---
title: <human title>
created: YYYY-MM-DD
updated: YYYY-MM-DD
date: YYYY-MM-DD HH:MM:SS ZONE
kind: code-session
status: complete | partial | blocked
session: <session UUID when observed>
transcript: <full path when observed>
working-directory: <path>
repos: <comma-separated repositories or none>
branches: <comma-separated branch mappings or none>
heads: <comma-separated repository=SHA mappings or none>
prs: <comma-separated PR references or none>
correlation: <caller-provided correlation identifier when present>
related: <comma-separated related knowledge paths when present>
---
```

Omit optional keys only when the value was not observed. Never invent a repository, branch, commit, PR, or transcript path.

## Required content

Use these sections when applicable:

1. **User request**: the initiating goal and material redirects.
2. **Session overview**: concise outcome and current state.
3. **Sequence of events**: chronological engineering work.
4. **Key findings**: important discoveries with file, commit, PR, issue, command, or log evidence.
5. **Technical decisions**: choices made and why.
6. **Repositories and files changed**: every observed repository and material path, including created, modified, renamed, and deleted files.
7. **Commits, branches, PRs, and tracker activity**: observed state and actions only.
8. **Tools and skills used**: important tool categories and any degraded behavior.
9. **Commands and automation**: critical commands or workflows and their results.
10. **Errors and failed approaches**: failure, cause, diagnostic clue, and resolution.
11. **Behavior changes**: before and after.
12. **Verification evidence**: command or check, expected result, actual result, and status.
13. **Risks and rollback**: when the work changed non-trivial behavior.
14. **Decisions not taken**: rejected alternatives when material.
15. **References**: source files, docs, issues, PRs, or URLs consulted.
16. **Open questions**: unresolved uncertainty.
17. **Next steps**: unfinished work, blockers, and the most useful continuation point.

Omit empty optional sections rather than filling them with boilerplate.

## Quality rules

- Facts only. Put uncertain claims under **Open questions**.
- Preserve material implementation detail and verification evidence.
- Distinguish work completed in this session from pre-existing state.
- Cite repository-specific findings with paths and line numbers when available.
- Record failed attempts honestly.
- Do not claim a test, build, CI check, deployment, or merge passed unless observed.
- Do not turn a coding log into an infrastructure maintenance log. When live infrastructure was also changed, let `wrap-session` create a paired maintenance record.

After writing, print the final absolute path and stop. Do not publish the artifact.
