---
name: log-homelab-maintenance
description: Create a factual homelab maintenance record for live infrastructure, hosts, services, networking, storage, security, deployments, upgrades, migrations, repairs, audits, and routine operations. Use when the user says "write a maintenance log", "log this homelab work", "document the deployment", "record this repair", or when wrap-session routes a session containing live operational changes. This skill writes the maintenance artifact only and never commits, pushes, deploys, restarts, or changes infrastructure.
allowed-tools: Read, Write, Bash
---

## Context

- Date: !`TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z'`
- Working directory: !`pwd`
- Transcript: !`ls -t ~/.claude/projects/$(pwd | sed 's|/|-|g')/*.jsonl 2>/dev/null | head -1`
- Knowledge root: !`printf '%s' "${HOMELAB_DOCS_ROOT:-$HOME/docs}"`
- Maintenance template: !`printf '%s' "${HOMELAB_DOCS_ROOT:-$HOME/docs}/maintenance/maintenance-log-template.md"`

# Log Homelab Maintenance

Create one curated operational record from work already performed in the session. Use the canonical maintenance template in the knowledge base as the schema source.

## Strict boundary

This skill may read evidence, perform read-only health checks needed to avoid a false completion claim, and write one maintenance artifact. It must not:

- edit Compose, proxy, system, service, network, storage, or application configuration;
- deploy, restart, stop, remove, or upgrade anything;
- stage, commit, push, merge, tag, or open a pull request;
- delete backups, branches, worktrees, logs, or runtime state;
- invent verification that did not occur.

## Read the knowledge contract

Before writing, read these files when present:

- `${HOMELAB_DOCS_ROOT:-$HOME/docs}/CLAUDE.md`
- `${HOMELAB_DOCS_ROOT:-$HOME/docs}/maintenance/CLAUDE.md`
- `${HOMELAB_DOCS_ROOT:-$HOME/docs}/maintenance/maintenance-log-template.md`

The template is canonical. This skill may adapt incident-oriented labels for planned operations, but it must preserve evidence, safety, changes, failed attempts, validation, completion, prevention, follow-ups, and post-mortem knowledge.

## Classify the maintenance record

Set `maintenance-type` to one of:

- `incident`
- `deployment`
- `migration`
- `upgrade`
- `audit`
- `repair`
- `hardening`
- `routine`

Choose from observed work, not wording alone.

## Resolve scope and output

1. A supplied `.md` path is the exact target.
2. A supplied non-path argument is the service or domain scope.
3. Otherwise infer the narrowest useful scope from observed hosts and services.
4. Default to `${HOMELAB_DOCS_ROOT:-$HOME/docs}/maintenance/<scope>/YYYY-MM-DD-short-description.md`.
5. Use `fleet` only when the operation materially crossed multiple domains and no narrower grouping is honest.
6. Never overwrite an existing file. Add a numeric suffix.

## Frontmatter

Use flat YAML frontmatter:

```yaml
---
title: <human title>
created: YYYY-MM-DD
updated: YYYY-MM-DD
date: YYYY-MM-DD
kind: homelab-maintenance
maintenance-type: incident | deployment | migration | upgrade | audit | repair | hardening | routine
host: <host or fleet>
services: <comma-separated services>
status: ongoing | partially-resolved | resolved | complete | blocked
session: <session UUID when observed>
transcript: <path when observed>
correlation: <caller-provided identifier when present>
related: <comma-separated related knowledge paths when present>
---
```

## Required content

Follow the canonical template and ensure the artifact answers:

1. What was requested, broken, changed, or maintained?
2. Which hosts, devices, services, users, and data were affected?
3. What evidence was used, including commands, logs, files, APIs, metrics, and external references?
4. What was the confirmed root cause or operational rationale?
5. What backups, snapshots, exports, or safety checks preceded changes?
6. What exact configuration, file, deployment, service, network, or runtime actions occurred, and why?
7. What attempts failed, and what evidence exposed the failure?
8. What health checks and runtime verification were observed afterward?
9. What is the honest completion state, rollback path, and data-loss risk?
10. What preventive actions, monitoring changes, documentation changes, and follow-ups remain?

For planned work, rename **Problem statement** in the body to **Change objective** when that is more accurate. Do not fabricate an incident.

## Completion rules

- Mark `resolved` or `complete` only when final runtime health was observed.
- When verification is missing, mark `ongoing`, `partially-resolved`, or `blocked` and state the missing proof.
- Cite backup identifiers and validation output precisely.
- Separate desired configuration from observed runtime state.
- Link paired code-session logs instead of duplicating repository details.

After writing, print the final absolute path and stop. Do not publish the artifact.
