---
name: full-review
description: Orchestrate a comprehensive, continuous multi-agent review across code quality, architecture, security, performance, testing, documentation, framework practices, and CI/CD, then produce one complete, deduplicated report artifact. Use when the user explicitly asks for a comprehensive, full, exhaustive, multi-agent, or multi-dimensional review of a repository, branch, diff, change set, or path. Security focus, performance criticality, strict mode, and framework selection are optional modifiers. Do not use for routine single-perspective reviews, narrow scans, or requests that only ask to fix already-known findings.
allowed-tools: Read Bash Grep Glob Task Write Edit
---

# Full Review

Run an evidence-backed, multi-phase code review with independent specialist perspectives as one uninterrupted batch. Use `.full-review/` only as transient, recoverable working state. Deliver the review as a validated report created through `artifacts:create-artifacts`.

## Required workflow

Before touching review artifacts, read [references/state-management.md](references/state-management.md) completely. When starting or resuming analysis, also read [references/reviewer-contract.md](references/reviewer-contract.md) and [references/workflow.md](references/workflow.md) completely and follow them in order. For inspection-only requests about an existing session, the state-management reference is sufficient unless analysis must resume.

Treat the user's text following the skill invocation as the review target and flags. If the user did not explicitly invoke the skill but the request clearly matches the description, infer the target from the conversation and current repository.

## Core rules

1. Resolve the repository root before creating `.full-review/`; all review artifacts belong at `<repo-root>/.full-review/`.
2. Preserve an incomplete existing session using the atomic state and resume rules in the state-management reference. Do not retain successful session scratch after delivery.
3. Validate and record the review scope internally before dispatching reviewers. This is not a user checkpoint. Ask only when the target cannot be resolved safely from the request and repository state.
4. Execute phases in order. Later reviewers must read the durable outputs of earlier phases instead of relying only on conversation memory.
5. Dispatch independent reviewers in parallel within a phase when agent capacity permits. Wrap every specialist with the shared reviewer contract; use a general read-only agent if a specialist cannot accept it.
6. Run scope, every review phase, consolidation, artifact creation, validation, and cleanup continuously. Do not pause for phase approval, present intermediate checkpoints, or ask whether to continue.
7. Record recoverable reviewer and tool failures in `failure_history` while continuing the current phase through safe retry or fallback. Use terminal `failed` only when the batch cannot create, validate, or index the required artifact. Never label incomplete coverage as complete.
8. Do not enter a separate planning mode automatically; this workflow is already the plan.
9. Keep subject code read-only unless the user separately authorizes fixes. Expected writes are review scratch under `.full-review/`, the final artifact, and its sealed artifact-owned evidence bundle created by `artifacts:create-artifacts`.
10. Findings need severity, file and line evidence, concrete impact, and a specific remediation. Do not report style preferences as defects.

## Runtime adaptation

- Claude Code: use parallel Task calls and proceed automatically between phases.
- Codex: use available parallel subagents and proceed automatically between phases. Map reviewer roles to installed specialized agents when possible.
- If parallel agents are unavailable, run the same independent reviewer prompts sequentially and record that limitation in the final metadata.

## Outputs

During execution, `.full-review/` contains these transient working files plus raw reviewer reports recorded by its manifest:

```text
.full-review/
├── state.json
├── 00-scope.md
├── scope.json
├── scope.patch                   # immutable diff evidence in diff mode
├── scope-files/                  # immutable copies when required
├── context-files/                # checksummed contextual evidence
├── context.json                  # immutable contextual-evidence manifest
├── coverage.json
├── artifacts.json
├── raw/
│   ├── 01-code-quality-<PARTITION>.md
│   ├── 01-architecture-<PARTITION>.md
│   ├── 02-security-<PARTITION>.md
│   ├── 02-performance-<PARTITION>.md
│   ├── 03-testing-<PARTITION>.md
│   ├── 03-documentation-<PARTITION>.md
│   ├── 04-framework-<PARTITION>.md
│   └── 04-operations-<PARTITION>.md
├── 01-quality-architecture.md
├── 02-security-performance.md
├── 03-testing-documentation.md
├── 04-best-practices.md
└── 05-consolidated-findings.md
```

After consolidation, invoke `artifacts:create-artifacts` and follow its current `SKILL.md`, content contract, `reports` type contract, evidence rules, and validation workflow. Create a repository-scoped report artifact containing every surfaced issue and the complete raw-to-canonical reconciliation. Before cleanup, copy the full review provenance into an artifact-owned model-run evidence bundle, seal it, and verify it. Validate the artifact, update and verify the artifact index, and write a durable delivery receipt into the evidence bundle. Only after all checks succeed may the exact `<repo-root>/.full-review/` directory be deleted. If artifact or evidence creation, sealing, validation, verification, or indexing fails, retain `.full-review/` for recovery.

The final response should lead with the verdict and severity counts, link the validated report artifact, identify the reviewers used, list any incomplete phase or evidence, and confirm whether scratch cleanup succeeded.
