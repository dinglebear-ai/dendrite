---
name: full-review
description: Orchestrate a comprehensive, checkpointed, multi-agent review across code quality, architecture, security, performance, testing, documentation, framework practices, and CI/CD, producing durable `.full-review/` artifacts and a prioritized report. Use when the user explicitly asks for a comprehensive, full, exhaustive, multi-agent, or multi-dimensional review of a repository, branch, diff, change set, or path. Security focus, performance criticality, strict mode, and framework selection are optional modifiers. Do not use for routine single-perspective reviews, narrow scans, or requests that only ask to fix already-known findings.
allowed-tools: Read, Bash, Grep, Glob, Task, Write, Edit
---

# Full Review

Run an evidence-backed, multi-phase code review with independent specialist perspectives and durable review artifacts.

## Required workflow

Before touching review artifacts, read [references/state-management.md](references/state-management.md) completely. When starting or resuming analysis, also read [references/reviewer-contract.md](references/reviewer-contract.md) and [references/workflow.md](references/workflow.md) completely and follow them in order. For inspection-only requests about an existing session, the state-management reference is sufficient unless analysis must resume.

Treat the user's text following the skill invocation as the review target and flags. If the user did not explicitly invoke the skill but the request clearly matches the description, infer the target from the conversation and current repository.

## Core rules

1. Resolve the repository root before creating `.full-review/`; all review artifacts belong at `<repo-root>/.full-review/`.
2. Preserve existing sessions using the safe sibling archive and atomic state rules in the state-management reference.
3. Confirm the review scope before dispatching reviewers. A path must exist; a descriptive target such as “recent changes” must be translated into an explicit file list or diff boundary.
4. Execute phases in order. Later reviewers must read the durable outputs of earlier phases instead of relying only on conversation memory.
5. Dispatch independent reviewers in parallel within a phase when agent capacity permits. Wrap every specialist with the shared reviewer contract; use a general read-only agent if a specialist cannot accept it.
6. Stop at both phase checkpoints and obtain explicit user direction before continuing.
7. On failure, atomically mark the session `failed` and preserve successful raw artifacts. Retry, skip, or produce a `partial` report only after explicit user direction; never label a partial review complete.
8. Do not enter a separate planning mode automatically; this workflow is already the plan.
9. Keep review work read-only unless the user separately authorizes fixes. `.full-review/` artifacts are the only expected writes during review.
10. Findings need severity, file and line evidence, concrete impact, and a specific remediation. Do not report style preferences as defects.

## Runtime adaptation

- Claude Code: use parallel Task calls and AskUserQuestion or an equivalent user prompt at checkpoints.
- Codex: use available parallel subagents and ask the user directly at checkpoints. Map reviewer roles to installed specialized agents when possible.
- If parallel agents are unavailable, run the same independent reviewer prompts sequentially and record that limitation in the final metadata.

## Outputs

The completed review must contain these primary artifacts plus raw reviewer reports recorded by the artifact manifest:

```text
.full-review/
├── state.json
├── 00-scope.md
├── scope.json
├── scope-files/                  # immutable copies when required
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
└── 05-final-report.md
```

The final response should lead with the verdict and severity counts, link the final report, identify the reviewers used, and list any phase or evidence that could not be completed.
