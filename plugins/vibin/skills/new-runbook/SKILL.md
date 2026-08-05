---
name: new-runbook
description: Create a reusable, evidence-backed homelab or development runbook from a proven procedure. Use when the user says "create a runbook", "turn this into a runbook", "document how to do this again", "write a recovery procedure", or asks for a repeatable operational workflow. Read related maintenance logs, session logs, decisions, standards, and current configuration before writing. This skill writes the runbook only and never executes the procedure or publishes the artifact.
allowed-tools: Read, Write, Bash
---

# New Runbook

Create a reusable procedure under the active knowledge root, normally `~/docs/runbooks/`.

## Boundary

- Do not execute the procedure while authoring it.
- Do not infer steps that were never verified.
- Do not commit or push the artifact.
- Do not copy secrets, tokens, raw logs, or ephemeral identifiers into the runbook.

## Sources

Read the knowledge-base contract and the narrowest relevant evidence:

- completed maintenance logs;
- code-session logs;
- accepted ADRs;
- standards and enforcement docs;
- current version-controlled configuration;
- official upstream documentation.

A runbook derived from one maintenance event must generalize carefully. Preserve host-specific constraints only when they are genuinely required.

## Frontmatter

Use `title`, `created`, `updated`, `status`, `kind: runbook`, `scope`, `validated-on`, `sources`, and `related` as flat values.

## Required sections

1. Purpose
2. Scope and exclusions
3. Preconditions
4. Required access and tools
5. Safety and backup checks
6. Procedure
7. Verification
8. Rollback
9. Known failure modes
10. Escalation or stop conditions
11. References and source logs
12. Revision triggers

Mark the runbook `draft` until its procedure and rollback have been observed or deliberately rehearsed. Print the final path and stop.
