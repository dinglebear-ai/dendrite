# Full Review

`full-review` converts the Comprehensive Review orchestrator into a portable Vibin skill for Claude Code and Codex. It runs independent, checkpointed phases for quality, architecture, security, performance, testing, documentation, framework practices, and operations.

## Examples

```text
Use full-review on this entire repository.
Run a comprehensive multi-agent review of the authentication diff --security-focus --strict-mode.
Do an exhaustive pre-PR review of src/payments --performance-critical.
```

It intentionally does not trigger for routine code reviews, narrow scans, or requests that only ask to fix known findings.

## Outputs and checkpoints

Review state and reports are written to `.full-review/`, which dirties the target working tree unless ignored locally. Raw reviewer outputs, stable finding IDs, coverage, checksums, summaries, and the final report are retained for safe resumption.

The workflow pauses after security/performance and before consolidation. Fixing code at a checkpoint supersedes the frozen review and requires a fresh session.

Flags: `--security-focus`, `--performance-critical`, `--strict-mode`, and `--framework <name>`. Strict mode blocks completion with unresolved P0/P1 findings, failed reviewers, unverified high-severity evidence, or incomplete eligible-file coverage.

## Provenance

Adapted from `comprehensive-review` version `1.3.1`, command `commands/full-review.md`. The conversion replaces command-only argument, named-agent, and checkpoint mechanics with portable skill instructions and adds raw persistence, stable IDs, atomic state, safe archival, frozen scope, and coverage accounting.
