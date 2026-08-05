---
name: align-standards
description: Measure repositories or homelab configuration against canonical standards, distinguish documented policy from actual enforcement, produce a drift report, and optionally reconcile explicitly selected gaps. Use when the user says "align standards", "audit repo standards", "check fleet drift", "standardize the Rust repos", or asks whether repositories match the policies in the knowledge base. Default to audit mode. Apply changes only when the user explicitly requests implementation.
allowed-tools: Read, Write, Edit, Bash
---

# Align Standards

Treat `~/docs` as the policy and rationale layer, `dinglebear-ai/workflows` as reusable enforcement, and live repositories as measured implementations.

## Modes

- Default: audit only. Write a drift report and change nothing outside the report.
- `--apply`: reconcile only observed, in-scope gaps after inventory and plan output.

## Workflow

1. Read relevant standards, ADRs, reports, and their stated enforcement mechanisms.
2. Identify the authoritative implementation in `~/workspace/workflows`, repository templates, CI, hooks, lints, or scripts.
3. Inventory selected repositories using tracked files only unless runtime state is explicitly in scope.
4. Measure practice and enforcement separately.
5. Classify each item as aligned, practice-only, declaration-only, drifted, exempt, unknown, or stale-standard.
6. Write a dated report under `~/docs/reports/standards/` with exact evidence.
7. In apply mode, use focused branches or worktrees, preserve repo-specific exemptions, run each repository's required gates, and update the report with final observed state.

Never claim fleet alignment from grep over dependencies, generated output, vendor trees, or build artifacts. Never rewrite a standard merely to match drift. When implementation disproves policy, surface the conflict for an explicit decision.
