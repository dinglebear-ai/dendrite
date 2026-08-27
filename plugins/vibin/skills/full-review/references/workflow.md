# Full Review Workflow

Follow every phase in order. Paths are relative to the repository root. Read `state-management.md` and `reviewer-contract.md` first.

Severity is stable across all artifacts: `Critical=P0`, `High=P1`, `Medium=P2`, and `Low=P3`. Never renumber findings during synthesis.

## Contents

1. Pre-flight and scope
2. Phase 1: quality and architecture
3. Phase 2: security and performance
4. Checkpoint 1
5. Phase 3: testing and documentation
6. Phase 4: best practices and operations
7. Checkpoint 2
8. Phase 5: consolidated report
9. Completion criteria

## 1. Pre-flight and scope

Use the project-root resolution, state machine, safe sibling archival, atomic writes, resume rules, and target-change invalidation procedure in `state-management.md`.

### Parse target and flags

Recognize:

- `--security-focus`
- `--performance-critical`
- `--strict-mode`
- `--framework <name>`

Determine the target from the remaining request. Verify paths exist. Translate descriptions such as `recent changes`, `authentication module`, a PR, or a branch into an immutable diff and explicit file manifest. Capture the VCS mode, reviewed commit, base, dirty patch hash, and tracked and eligible-untracked file hashes before creating `.full-review/`. Freeze eligible untracked contents under `.full-review/scope-files/` as specified by `state-management.md`. Outside Git, use snapshot mode and a complete frozen content manifest. Exclude `.full-review/**` and `.full-review-archive/**` unless explicitly targeted. Confirm the frozen scope before dispatch.

For large targets, partition by subsystem or bounded file batches. Assign each partition a deterministic ID namespace and record it with assigned, inspected, skipped, generated, vendored, unsupported, and excluded files in `.full-review/coverage.json`. Never claim exhaustive coverage unless all eligible files were inspected; report coverage percentage and limitations.

Initialize immutable `scope.json` plus mutable `coverage.json`, `state.json`, and `artifacts.json` exactly as specified by `state-management.md`.

Write `.full-review/00-scope.md`:

```markdown
# Review Scope

## Target
[Target and diff boundary]

## Files
[Explicit paths]

## Frozen Evidence
- VCS mode
- Reviewed commit
- Diff base
- Patch SHA-256
- Scope manifest SHA-256
- Excluded review artifact paths

## Flags
- Security Focus: yes/no
- Performance Critical: yes/no
- Strict Mode: yes/no
- Framework: value or auto-detected

## Review Phases
1. Code Quality & Architecture
2. Security & Performance
3. Testing & Documentation
4. Best Practices & Standards
5. Consolidated Report
```

Atomically record immutable `scope.json` and `00-scope.md` with checksums in `artifacts.json`; atomically initialize mutable `coverage.json` without a manifest checksum; then transition state to `phase_1`.

## 2. Phase 1: quality and architecture

Run the following reviewers independently and in parallel. Prepend `reviewer-contract.md` and pass the frozen manifest with the mode-appropriate immutable evidence: the frozen diff in diff mode or checksummed frozen file copies in snapshot mode. Never recompute scope from the mutable checkout.

### Code quality reviewer

Review the scope for:

1. Cyclomatic and cognitive complexity, nesting, and oversized functions.
2. Naming, cohesion, maintainability, and debuggability.
3. Duplicated behavior that can drift or has already caused defects.
4. SOLID violations, code smells, and established project-pattern violations.
5. Technical debt that materially increases change risk.
6. Missing, swallowed, misleading, or inconsistent error handling.

Use the assigned partition namespace and stable `QUA-<PARTITION>-###` IDs with the shared finding schema. Reject style-only findings.

### Architecture reviewer

Review the scope for:

1. Component boundaries and separation of concerns.
2. Dependency direction, inappropriate coupling, and cycles.
3. API contracts, schemas, versioning, and error behavior.
4. Data models, persistence boundaries, and consistency.
5. Appropriate patterns, missing abstractions, and over-engineering.
6. Consistency with repository architecture and deployment topology.

Use the assigned partition namespace and stable `ARC-<PARTITION>-###` IDs with the shared finding schema, including architectural impact.

Persist one unmodified output per dispatch to `.full-review/raw/01-code-quality-<PARTITION>.md` and `.full-review/raw/01-architecture-<PARTITION>.md` before synthesis. Atomically register every partition artifact and checksum in `artifacts.json`; build each consolidated role section from all registered partition artifacts.

Consolidate and deduplicate both reports into `.full-review/01-quality-architecture.md`:

```markdown
# Phase 1: Code Quality & Architecture Review

## Code Quality Findings
[By severity, preserving QUA IDs]

## Architecture Findings
[By severity, preserving ARC IDs]

## Critical Issues for Phase 2 Context
[Security/performance-relevant findings]
```

Update coverage with files actually inspected. Record the consolidated artifact and atomically transition to `phase_2`.

## 3. Phase 2: security and performance

Both reviewers read `00-scope.md` and `01-quality-architecture.md` and receive the shared contract, frozen evidence, and coverage assignments.

### Security reviewer

Analyze:

1. OWASP Top 10 and applicable CWE classes.
2. Input validation, injection, redirects, path traversal, archives, and deserialization.
3. Authentication, authorization, privilege boundaries, and session management.
4. Cryptography, secret handling, and sensitive-data exposure.
5. Dependency vulnerabilities and unsafe versions.
6. Configuration, CORS, headers, logging, and production defaults.

Use the assigned partition namespace and stable `SEC-<PARTITION>-###` IDs with the shared schema, adding CVSS and CWE when meaningful. Security-focus mode broadens caller and consumer tracing.

Dependency vulnerability claims require an ecosystem-native audit or current authoritative advisory. Record command, advisory database timestamp, package/version, advisory ID, and source. If unavailable, mark dependency security `unverified` instead of filing a speculative vulnerability.

### Performance reviewer

Analyze:

1. Database access, N+1 behavior, indexes, and pool use where applicable.
2. Unbounded memory, large allocations, leaks, and lifecycle cleanup.
3. Cache correctness and invalidation.
4. Blocking I/O, pagination, payload limits, and backpressure.
5. Races, locks, contention, deadlocks, and serialized bottlenecks.
6. Frontend rendering and bundle behavior where applicable.
7. Scale at roughly 10x, 100x, and 1000x current inputs.

Use the assigned partition namespace and stable `PER-<PARTITION>-###` IDs with the shared schema, adding complexity and scale impact. Performance-critical mode requires reproduced or two-source evidence for P0/P1 resource claims.

Persist one unmodified output per dispatch to `.full-review/raw/02-security-<PARTITION>.md` and `.full-review/raw/02-performance-<PARTITION>.md` before synthesis. Register every partition artifact and checksum; synthesize each role from all of its registered partition artifacts.

Consolidate and deduplicate into `.full-review/02-security-performance.md`:

```markdown
# Phase 2: Security & Performance Review

## Security Findings
[By severity, preserving SEC IDs]

## Performance Findings
[By severity, preserving PER IDs]

## Critical Issues for Phase 3 Context
[Testing/documentation implications]
```

Update coverage, record the phase artifact, and atomically transition to `checkpoint_1`.

## 4. Checkpoint 1

Summarize Phase 1 and Phase 2 counts by category and severity. Point the user to both artifacts and ask for exactly one direction:

1. Continue to testing and documentation.
2. Fix critical issues before continuing.
3. Pause and preserve progress.

Strict mode blocks continuation or completion with unresolved P0/P1 findings, failed reviewers, unverified P0/P1 evidence, or incomplete eligible-file coverage. Otherwise recommend fixes when Critical findings exist. Do not start Phase 3 without approval.

If fixes are authorized, mark this frozen session `superseded`, implement and verify separately, then start a fresh review. Never feed stale pre-fix artifacts into later phases.

## 5. Phase 3: testing and documentation

Both reviewers read prior artifacts and receive the shared contract, frozen evidence, and assigned coverage partitions.

### Testing reviewer

Evaluate:

1. Coverage of critical behavior and failure paths.
2. Behavioral versus implementation-coupled assertions.
3. Unit, integration, end-to-end, and property-test balance.
4. Boundary, malformed-input, concurrency, partial-failure, and recovery cases.
5. Isolation, fixtures, mocks, nondeterminism, and flaky-test signals.
6. Tests required by security findings.
7. Load or benchmark gaps required by performance findings.

Use the assigned partition namespace and stable `TST-<PARTITION>-###` IDs with the shared schema, adding a concrete proposed test.

### Documentation reviewer

Evaluate:

1. Comments for complex invariants and algorithms.
2. API requests, responses, schemas, errors, and examples.
3. Architecture decisions, diagrams, and component contracts.
4. Setup, development, deployment, and troubleshooting instructions.
5. Drift between documentation and implementation.
6. Changelogs and migration guidance for breaking behavior.

Use the assigned partition namespace and stable `DOC-<PARTITION>-###` IDs with the shared schema, adding the specific documentation correction.

Persist one unmodified output per dispatch to `.full-review/raw/03-testing-<PARTITION>.md` and `.full-review/raw/03-documentation-<PARTITION>.md` before synthesis. Register every partition artifact and checksum; synthesize each role from all of its registered partition artifacts.

Write `.full-review/03-testing-documentation.md` with severity-ordered sections preserving IDs. Update coverage, record all artifacts, and transition to `phase_4`.

## 6. Phase 4: best practices and operations

Both reviewers read all prior artifacts and receive the shared contract, frozen evidence, and coverage assignments.

### Framework and language reviewer

Check idioms, current framework conventions, deprecated APIs, safe modernization opportunities, dependency hygiene, and production build configuration. Respect `--framework`; otherwise detect frameworks. Use the assigned partition namespace and stable `FRM-<PARTITION>-###` IDs with the shared schema, adding current-versus-recommended behavior and migration guidance.

### CI/CD and operations reviewer

Check build/test gates, security scanning, deployment and rollback, infrastructure as code, telemetry and alerting, incident/runbook readiness, environment separation, and secret management. Use the assigned partition namespace and stable `OPS-<PARTITION>-###` IDs with the shared schema, adding operational impact.

Persist one unmodified output per dispatch to `.full-review/raw/04-framework-<PARTITION>.md` and `.full-review/raw/04-operations-<PARTITION>.md` before synthesis. Register every partition artifact and checksum; synthesize each role from all of its registered partition artifacts.

Write `.full-review/04-best-practices.md`:

```markdown
# Phase 4: Best Practices & Standards

## Framework & Language Findings
[By severity]

## CI/CD & DevOps Findings
[By severity]
```

Update coverage, record all artifacts, and atomically transition to `checkpoint_2`.

## 7. Checkpoint 2

Show new Phase 3 and Phase 4 counts plus the cumulative Critical and High findings. Ask whether to:

1. Generate the consolidated report.
2. Fix critical/high issues first.
3. Pause and preserve progress.

Re-evaluate every strict-mode gate using all four phases. Unresolved P0/P1 findings, failed reviewers, unverified P0/P1 evidence, or incomplete eligible-file coverage block completion. Do not start Phase 5 without approval. Authorized fixes supersede the session and require a fresh review.

## 8. Phase 5: consolidated report

Read every raw and consolidated artifact from `artifacts.json`. Build the pre-deduplication inventory exclusively from raw artifacts, including authorized failed/skipped placeholders in partial sessions. For every stable ID or placeholder, mark it included, duplicate, contextual/pre-existing, inapplicable, unsupported, failed, or skipped, with a reason and canonical duplicate target. In-scope findings drive the verdict; contextual findings are separate unless they block safe integration.

Write `.full-review/05-final-report.md`:

```markdown
# Comprehensive Code Review Report

## Review Target
[Scope and diff boundary]

## Executive Summary
[Overall health, verdict, major risks]

## Findings by Priority

### Critical Issues (P0 — Must Fix Immediately)
[Security, data loss, auth bypass, production stability]

### High Priority (P1 — Fix Before Next Release)
[Major bottlenecks, test gaps, architecture risks, vulnerable dependencies]

### Medium Priority (P2 — Plan for Next Sprint)
[Optimizations, documentation gaps, refactors, test quality]

### Low Priority (P3 — Track in Backlog)
[Minor smells and optional improvements]

## Findings by Category
- Code Quality: counts
- Architecture: counts
- Security: counts
- Performance: counts
- Testing: counts
- Documentation: counts
- Best Practices: counts
- CI/CD & DevOps: counts

## Recommended Action Plan
1. Ordered, grouped actions starting with P0/P1.
2. Relative effort: small, medium, or large.
3. Validation required for each action.

## Review Metadata
- Review date
- VCS mode
- Scope mode
- Reviewed commit and diff boundary, when VCS mode is Git
- Snapshot scope SHA-256, when scope mode is snapshot
- Phases completed
- Flags
- Reviewers used
- Commands and tests run
- Evidence unavailable
- Coverage counts and percentage
- Strict-mode gates

## Inventory Reconciliation
- Raw finding IDs by reviewer
- Included findings
- Duplicates
- Discarded/inapplicable findings with reasons
```

Verify the target fingerprint and re-evaluate every strict-mode gate immediately before the terminal transition. Record each gate and pass/fail evidence in final metadata. Then record the report and ledger and transition to `complete` only when every gate passes. Explicit skips use `partial`; unresolved strict failures lead to `failed`, `partial`, or `superseded`, never `complete`.

## 9. Completion criteria

The review is complete only when:

- Scope and flags are explicit.
- All four analysis phases ran for `complete`; user-authorized incomplete output is `partial`.
- Both user checkpoints were honored.
- Every required immutable scope, raw, consolidated, and final artifact exists with a checksum in `artifacts.json`; authorized partial sessions use durable failed/skipped raw placeholders.
- Every reported finding has severity, path/line evidence, impact, and remediation.
- The inventory reconciles every stable raw finding ID.
- Coverage records every eligible file as inspected, skipped, generated, vendored, unsupported, or excluded.
- The frozen target fingerprint still matches, or the session is `superseded`.
- The final report provides counts, verdict, action order, reviewer list, and verification limitations.

Present the final report path and a compact severity summary. Do not claim files were fixed unless the user separately authorized implementation and the fixes were verified.
