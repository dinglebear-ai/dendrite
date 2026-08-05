---
name: log-decisions
description: Record one or more durable architecture or operational decisions as ADRs in the personal knowledge base. Use when the user says "log this decision", "create an ADR", "record why we chose this", "capture these decisions", or when a session produced choices that future agents would otherwise relitigate. Read the ADR contract and related evidence, create the next numbered ADR files, and link superseded decisions. This skill writes decision records only and never implements, commits, or publishes them.
allowed-tools: Read, Write, Edit, Bash
---

# Log Decisions

Create durable ADRs under `~/docs/decisions/` using the repository's current ADR template and numbering convention.

## Decision test

Create an ADR only when the choice is durable, consequential, and likely to be questioned later. Do not create ADRs for temporary debugging steps, routine commands, or facts already governed by an accepted decision.

## Workflow

1. Read `~/docs/CLAUDE.md`, the decisions index, template, and related ADRs.
2. Recover the decision context, alternatives, evidence, implementation state, and enforcement mechanism.
3. Split materially independent choices into separate ADRs.
4. Determine the next zero-padded ADR number from tracked files, not only the index.
5. When replacing an accepted decision, create a new ADR with `supersedes` and update only the old ADR's status and `superseded-by` pointer.
6. Do not rewrite accepted ADR rationale to make history look cleaner.

## Required content

Use the repository-required frontmatter and these sections:

- Status
- Context
- Decision
- Consequences
- Alternatives considered
- Enforcement
- Validation or adoption evidence
- Sources
- Related plans, reports, sessions, maintenance logs, and configuration

If enforcement does not exist, state that the decision is advisory. Print every created or updated path and stop without publishing.
