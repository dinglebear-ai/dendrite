# Full Review Workflow

Follow every phase in order as one uninterrupted batch. Paths are relative to the repository root. Read `state-management.md` and `reviewer-contract.md` first. Do not stop for phase checkpoints or ask the user whether to continue.

Severity is stable across all artifacts: `Critical=P0`, `High=P1`, `Medium=P2`, and `Low=P3`. Never renumber findings during synthesis.

## Contents

1. Pre-flight and scope
2. Phase 1: quality and architecture
3. Phase 2: security and performance
4. Phase 3: testing and documentation
5. Phase 4: best practices and operations
6. Phase 5: consolidate and deduplicate every finding
7. Create and validate the report artifact
8. Clean up scratch and complete

## 1. Pre-flight and scope

Use the project-root resolution, state machine, safe sibling archival, atomic writes, resume rules, and target-change invalidation procedure in `state-management.md`.

### Parse target and flags

Recognize:

- `--security-focus`
- `--performance-critical`
- `--strict-mode`
- `--framework <name>`

Determine the target from the remaining request. Verify paths exist. Translate descriptions such as `recent changes`, `authentication module`, a PR, or a branch into an immutable diff and explicit file manifest. Capture the VCS mode, reviewed commit, base, dirty patch hash, and tracked and eligible-untracked file hashes before creating `.full-review/`. Store the immutable diff at `.full-review/scope.patch`; freeze eligible untracked contents under `.full-review/scope-files/`. Build the frozen contextual-evidence manifest and copies required by each review dimension. Outside Git, use snapshot mode and a complete frozen content manifest. Exclude `.full-review/**` and `.full-review-archive/**` as subject code. Validate and record the frozen scope internally, then dispatch without a user approval step.

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

Update coverage, record the phase artifact, and atomically transition directly to `phase_3`. Critical findings affect the verdict and action order; they do not pause the review.

## 4. Phase 3: testing and documentation

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

## 5. Phase 4: best practices and operations

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

Update coverage, record all artifacts, and atomically transition directly to `consolidation`.

## 6. Phase 5: consolidate and deduplicate every finding

Read every raw and consolidated artifact from `artifacts.json`. Build the pre-deduplication inventory exclusively from raw artifacts, including failed/skipped placeholders in partial sessions. Account for every stable ID or placeholder.

Deduplicate only findings with the same root cause, affected behavior, and consequence. Select one canonical finding, retain the highest supported severity, and merge all unique absolute locations, causal traces, verbatim observed outputs, evidence classes, proof boundaries, consulted revisions and hashes, other evidence, impacts, remediations, validation requirements, reviewer roles, and source IDs into it. Similar symptoms with different causes or fixes remain separate findings. Never discard a finding merely because another reviewer reported it. For every raw ID, record exactly one disposition: canonical, merged into a named canonical ID, contextual/pre-existing, inapplicable with reason, unsupported with reason, failed, or skipped. Reconcile raw, canonical, and disposition counts so no issue can disappear during synthesis.

Write `.full-review/05-consolidated-findings.md` as the complete content source for the final artifact:

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
- Canonical findings
- Merged duplicate IDs with their canonical target
- Discarded/inapplicable findings with reasons
```

Append a complete raw-findings ledger. Every raw record, including contextual, unsupported, inapplicable, failed, and skipped entries, retains its title, original severity, absolute locations, causal trace, observed output, evidence class, impact, proof boundary, validation request, consulted hashes, source reviewer, disposition, and disposition rationale. A merged entry may point to its canonical record only after every unique detail has been copied into the canonical record.

Verify the target fingerprint and evaluate every strict-mode gate. Strict failures set the artifact verdict to `NOT READY` and affect release advice; they never stop consolidation, artifact production, validation, indexing, evidence sealing, or cleanup. Record each gate and its evidence in the consolidated source, register its checksum, and transition to `artifact_creation`.

## 7. Create and validate the report artifact

Invoke `artifacts:create-artifacts` and follow its current `SKILL.md` completely. Resolve the actual subject repository and create an artifact of type `reports` under the routed repository artifact root. Read and follow the artifact content contract, report type contract, evidence contract, and design contract. Use the report template selected by that skill; do not hand-roll a replacement report in `.full-review/`.

Populate the artifact from `05-consolidated-findings.md` and the registered evidence. The artifact must contain:

- the target, verdict, severity and category counts, coverage, review flags, reviewers, commands, tests, limitations, and strict-mode gate results;
- every canonical finding with severity, stable canonical ID, all source IDs, every absolute affected location, causal trace, verbatim observed output, evidence class, proof boundary, consulted revisions and hashes, other evidence, impact, remediation, and validation requirement;
- contextual findings in a separate section;
- a complete raw-findings ledger preserving the full substance and disposition of unsupported, inapplicable, contextual, failed, and skipped records;
- the full raw-to-canonical reconciliation, including every duplicate mapping and every non-finding disposition with its reason;
- count checks showing that all raw IDs equal canonical IDs plus merged and otherwise dispositioned IDs.

Before deleting scratch, run `artifacts.py evidence-start "$ARTIFACT" --kind model-run`. Copy the frozen scope and context manifests, `scope.patch`, immutable target/context copies, reviewer prompts and shared contract, reviewer identities and model settings, every raw output and failed placeholder, coverage, failure history, consolidated source, and command receipts into the run's `raw/` and `derived/` directories according to the evidence contract. Link the evidence bundle from the report.

Run initial path and content validation and inspect the report at desktop and phone widths. This validation is provisional until evidence sealing is complete.

If creation, rendering, evidence sealing/verification, validation, indexing, or index lookup fails after safe retry, mark the session `failed`, retain `.full-review/`, and report the failure. Do not delete recoverable evidence.

## 8. Clean up scratch and complete

Before cleanup, add an intent receipt to the unsealed evidence run containing artifact identity, repository identity, reconciliation counts, intended cleanup target, and timestamp; do not claim sealing, verification, or cleanup has occurred. Run `evidence-seal` and `evidence-verify`, capturing their commands, timestamps, exit codes, and verbatim outputs in `.full-review/evidence-receipts.txt`. Add those receipts and the verified evidence-bundle path to the final report, then rerun artifact path/content validation, update the index, and verify the intended artifact card by stable artifact ID and path. Record the final artifact SHA-256 and all final validation, index, lookup, seal, and verification receipts in `.full-review/artifacts.json`, then transition to `ready_for_cleanup`.

Immediately before removal, verify every prerequisite. Resolve the repository root again, verify the target is exactly `<repo-root>/.full-review/`, remove that directory and no sibling path, and verify it no longer exists. Report the observed cleanup result in the final response. The surviving artifact and verified model-run bundle are the durable review proof; cleanup is proven by the post-removal filesystem check during the run.

## 9. Completion criteria

The review is complete only when:

- Scope and flags are explicit.
- All four analysis phases ran for `complete`; incomplete coverage is `partial`.
- The workflow ran continuously without phase checkpoints.
- Every required immutable scope, raw, and consolidated scratch artifact existed with a checksum before cleanup; partial sessions used durable failed/skipped raw placeholders while the artifact was built.
- Every reported finding has severity, path/line evidence, impact, and remediation.
- The inventory reconciles every stable raw finding ID.
- Coverage records every eligible file as inspected, skipped, generated, vendored, unsupported, or excluded.
- The frozen target fingerprint still matches, or the session is `superseded`.
- A complete, deduplicated report was created through `artifacts:create-artifacts`, validated, indexed, and includes every surfaced issue in its full raw ledger and reconciliation.
- A linked artifact-owned model-run bundle preserves all review provenance and passed `evidence-seal` and `evidence-verify`.
- `.full-review/` was removed only after the artifact and reconciliation checks succeeded.

Present the validated artifact path and a compact severity summary. State whether cleanup succeeded. Do not claim files were fixed unless the user separately authorized implementation and the fixes were verified.
