---
name: wrap-session
description: Route session closeout to the correct domain logger based on observed work. Use when the user says "wrap session", "wrap up this session", "log what we did", "close out", or invokes /wrap-session. Classify the full session as coding, homelab maintenance, or both, invoke log-code-session and/or log-homelab-maintenance, cross-link paired artifacts, refresh knowledge indexes, and validate the knowledge base. This skill never commits, pushes, merges, or performs cleanup.
allowed-tools: Read, Write, Edit, Bash
---

## Context

- Date: !`TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z'`
- Working directory: !`pwd`
- Transcript: !`ls -t ~/.claude/projects/$(pwd | sed 's|/|-|g')/*.jsonl 2>/dev/null | head -1`
- Knowledge root: !`printf '%s' "${HOMELAB_DOCS_ROOT:-$HOME/docs}"`

# Wrap Session

Close the session by creating the right durable knowledge artifacts. Read `references/routing.md` before classifying.

## Boundary

This router coordinates logging and knowledge-base validation only. It must not stage, commit, push, merge, tag, mutate trackers, move plans, clean branches or worktrees, deploy services, or change infrastructure.

## Workflow

1. Recover the full session from the current conversation and transcript when available.
2. Inventory observed actions and evidence across the entire session, including earlier context that may no longer be visible.
3. Classify the session:
   - `code`: repository, source, build, test, CI, PR, release, packaging, or code-review work.
   - `maintenance`: live host, service, network, storage, security, deployment, migration, upgrade, repair, or operational verification work.
   - `both`: material work occurred in both domains.
   - `none`: no durable coding or operational work occurred.
4. Generate one correlation identifier. Prefer the transcript UUID; otherwise use `YYYYMMDD-HHMMSS-<slug>`.
5. Invoke the selected domain logger or loggers and pass the correlation identifier plus any caller output hint.
6. When both artifacts are created:
   - add each artifact's relative path to the other's flat `related:` frontmatter value;
   - keep domain details in the appropriate artifact rather than duplicating whole sections;
   - verify both carry the same `correlation:` value.
7. Refresh deterministic indexes when the knowledge root provides a generator:
   - `python3 <knowledge-root>/scripts/docs_indexes.py`
   - `<knowledge-root>/maintenance/refresh-maintenance-index.sh` when a maintenance log was written.
8. Run `python3 <knowledge-root>/scripts/docs_doctor.py` when available.
9. Return:
   - selected route and the evidence that triggered it;
   - absolute artifact paths;
   - validation results;
   - possible follow-on artifacts such as an ADR, runbook, report, or standards alignment.

## Invocation

Prefer invoking the installed `log-code-session` and `log-homelab-maintenance` skills. When the runtime cannot invoke sibling skills directly, read their sibling `SKILL.md` files and follow their contracts exactly. Do not reintroduce legacy `save-to-md` behavior.

## No automatic secondary artifacts

Do not automatically create an ADR, runbook, report, or standards change merely because one might be useful. Recommend the appropriate skill and explain the evidence. Create it only when the user requested it or the current request explicitly includes it.

If the route is `none`, do not create filler logs. Explain that no durable code or maintenance artifact was warranted.
