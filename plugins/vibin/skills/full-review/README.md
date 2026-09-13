# Full Review

`full-review` converts the Comprehensive Review orchestrator into a portable Vibin skill for Claude Code and Codex. It runs independent phases for quality, architecture, security, performance, testing, documentation, framework practices, and operations as one continuous batch.

## Examples

```text
Use full-review on this entire repository.
Run a comprehensive multi-agent review of the authentication diff --security-focus --strict-mode.
Do an exhaustive pre-PR review of src/payments --performance-critical.
```

It intentionally does not trigger for routine code reviews, narrow scans, or requests that only ask to fix known findings.

## Output

Transient review state is written to `.full-review/` for recovery while the review runs. Raw reviewer outputs, stable finding IDs, coverage, checksums, and summaries are consolidated and deduplicated into one report created and validated with `artifacts:create-artifacts`.

The workflow does not pause between phases. After the final artifact validates and is indexed, it removes `.full-review/`. Failed artifact creation or validation leaves the scratch directory intact for recovery.

Flags: `--security-focus`, `--performance-critical`, `--strict-mode`, and `--framework <name>`. Strict mode turns unresolved P0/P1 findings, failed reviewers, unverified high-severity evidence, or incomplete eligible-file coverage into a prominent `NOT READY` verdict; it does not stop report production or successful cleanup.

## Provenance

Adapted from `comprehensive-review` version `1.3.1`, command `commands/full-review.md`. The conversion replaces command-only argument, named-agent, and checkpoint mechanics with portable skill instructions and adds stable IDs, atomic state, frozen scope, artifact-owned evidence, and coverage accounting.
