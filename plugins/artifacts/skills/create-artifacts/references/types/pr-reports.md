# pr-reports/

The canonical private lifecycle record for one pull request submitted to an
project repository. A PR report is a standalone HTML guide,
evidence package, decision record, implementation map, test dossier, and
handoff. It must let a reviewer reconstruct the work from the first discussion
through the current committed PR without relying on chat history or author
memory.

This directory contains sensitive local provenance by design. A PR report is
not part of the public PR payload unless separately sanitized and explicitly
approved for publication.

## Source hierarchy

Claims and decisions may rely only on:

1. Reproducible firsthand observations and exact command output.
2. The target repository's code, tests, configuration, history, and runtime.
3. Primary official documentation, specifications, release notes, or source.

Secondary posts, comments, issues, and prior PRs may supply context but cannot
be the sole proof of a technical claim. Label inference separately from
observation. Do not expose hidden chain-of-thought or private model reasoning;
record the reviewable decision rationale instead: evidence considered, options,
tradeoffs, selected outcome, and falsifier.

## Required report contract

Every report keeps all template sections and completely covers:

- **Public summary:** a separately audited, allowlisted summary that is safe to
  copy into a public PR. Its presence is not publication authorization.

- **Problem and impact:** the issue or feature, why it matters, affected users,
  scope, expected behavior, observed behavior, and a minimal reproduction.
- **Provenance:** repository, PR URL/number and state, base and head branches,
  base and head SHAs, merge base, start/update timestamps with time zone,
  absolute worktree path, host/runtime/toolchain facts, dirty-state caveats, and
  target environments. Never print a credential while collecting this data.
- **Lifecycle:** first discussion, investigation, proposal/spec/plan, worktree
  creation, implementation waves, review, remediation, verification, commits,
  publication, CI, and current state. Record abandoned approaches and resets.
- **Report revisions:** report revision, timestamp, head SHA, changed sections,
  reason, and prior digest. This records the dossier's history, not source work.
- **Decisions:** one ledger row per material decision with the question, options,
  evidence, chosen option, why alternatives lost, consequences, rollback, and
  what new evidence would reverse the decision.
- **Changes:** every touched file, its responsibility, why it changed, the exact
  targeted behavior, generated/manual status, and corresponding tests. Explain
  deletions and files deliberately left unchanged.
- **Coverage:** declare the authoritative denominator for requirements, files,
  routes, plugins, environments, tests, review comments, and documentation;
  map every requirement ID to implementation paths, test IDs, evidence IDs, and
  state. “All” is forbidden without a named denominator.
- **Dependencies and versions:** every added, removed, replaced, or updated
  dependency/package/runtime; purpose, exact before/after versions, transitive
  or lockfile effect, license/security/maintenance considerations, rejected
  alternatives, and why existing repository facilities were insufficient.
- **Repository patterns:** the existing project abstractions, modules, design
  system, error contracts, test helpers, workflows, and conventions reused.
  Any hand-rolled pattern must cite the search performed and explain why no
  owned pattern fit. “Simpler” alone is not justification.
- **Testing:** an extensive layered matrix covering focused unit, integration,
  contract, property/race/recovery/security/performance tests as applicable;
  full repository gates; browser/QA/E2E behavior where applicable; changed-test
  integrity; seeds/repetitions; exact commands, environment, expected and actual
  results, duration, timestamp, and evidence location. Separate branch-caused
  failures, pre-existing failures, environment blockers, and tests not run.
- **Targeted proof:** a clean-room reproduction that fails on the exact base,
  passes on the exact head, exercises the real affected boundary, guards against
  adjacent false positives, and states its proof boundary. “Tests pass” is not
  irrefutable proof without a base/head contrast and scope control.
- **Documentation:** documents created, updated, reviewed but unchanged, still
  required, and explicitly not required; include product docs, developer docs,
  API/contracts, release notes/changelogs, migration notes, and comments.
- **Agents and sessions:** product agents used (Codex, Claude, Gemini, human,
  etc.; not transient subagent names), model/version when known, role, session
  IDs, absolute transcript paths, time range, outcome, and continuity gaps.
- **Authorship and independence:** stable claim IDs, claim author, verifier,
  session/worktree separation, verification evidence, and assurance level.
- **Tooling:** MCP servers/tools/prompts/resources, skills, slash commands,
  agents, scripts, browsers, external services, and other primitives used;
  purpose, relevant inputs/outputs, limitations, failures, retries, and fallback.
- **Issues and mistakes:** implementation issues, tool failures, wrong turns,
  repeated mistakes with root cause and prevention, and pre-existing issues.
  Never recast an untested hypothesis as a diagnosis.
- **Disagreements:** preserve conflicts among code, runtime, docs, tools, agents,
  and reviewers; record which authority prevailed, why, and remaining doubt.
- **Unacted findings:** severity, evidence, relevance, why deferred or excluded,
  owner/tracking link, and the trigger for revisiting. Preserve rejected claims
  and why they failed the proof pass.
- **Risks and opportunities:** regression, security, privacy, compatibility,
  migration, lifecycle, concurrency, recovery, performance, operability,
  maintainability, dependency, documentation, and release risks; mitigations,
  residual risk, possible optimizations, and intentionally deferred enhancement.
- **Follow-up:** all blocking pre-review/pre-merge work and non-blocking
  post-merge/release/cleanup/monitoring work, each with owner, tracker, trigger,
  validation, and status. A report cannot call required work optional.
- **References and related artifacts:** every repository, URL, official doc,
  specification, post, issue, PR, review comment, Linear item, commit, source
  location, report, research artifact, proposal, spec, plan, session, and
  durable doc actually consulted. Pin mutable sources to a version or SHA.
- **Evidence integrity:** stable evidence IDs, kind, absolute path or pinned URL,
  SHA-256, producer, exact command, source SHA, timestamp, manifest digest, and
  normalized report digest.
- **Review closure:** every material review thread, affected SHA/path, concern,
  disposition, resulting commit, verification, and underlying-concern state.
  Closing a conversation does not prove the concern resolved.
- **Post-review changes:** every later commit, why it was needed, which evidence
  and conclusions it invalidated, and what was rerun.
- **Learnings and highlights:** useful repository/stack/environment/workflow
  knowledge, especially good ideas and decisions, repeated-error prevention,
  and facts worth promoting to durable documentation.
- **Disclosure boundary:** secrets/PII scan, private local details, public payload
  audit, publication authorization, and a list of report content that must not
  be copied into the public PR.
- **Artifact quality:** semantic headings, accessible tables, keyboard behavior,
  focus, responsive layouts, reduced motion, light/dark themes, print, font
  fallback, standalone/offline behavior, and portable export.

## Stable identifiers and states

Use monotonically assigned IDs that never change after publication:

```text
REQ-001 requirement     CLM-001 claim          DEC-001 decision
TEST-001 verification  E-001 evidence         RISK-001 risk
REV-001 review thread  FUP-001 follow-up      DIS-001 disagreement
```

Allowed machine states are exactly `PASS`, `FAIL`, `BLOCKED`, `NOT RUN`, `NOT
APPLICABLE`, `UNKNOWN`, and `STALE`. Every state except `PASS` includes a reason.
`NOT APPLICABLE` cites the rule or scope fact that makes it inapplicable.
`BLOCKED` names the external condition. `STALE` names the newer SHA/event.

## Source ownership

The report is the canonical map, not the independent owner of every mutable
fact:

| Fact | Authority |
| --- | --- |
| PR state, checks, and review threads | GitHub |
| source head, base, merge base, and commits | repository object database |
| requirements | linked issue/spec/contract |
| implementation sequencing | linked plan |
| test output and runtime captures | hashed retained evidence |
| session history | transcript/session artifact |
| final cross-source rationale and disposition | PR report |

Summaries name their authority, version, and capture time. When authorities
disagree, preserve the conflict instead of silently choosing convenient data.

## Staleness and readiness

`accepted` is invalid and must be treated as `STALE` when any of these occurs:

- the live PR head differs from `artifact.head`;
- the merge base changes materially;
- decisive tests, proof, or final review cover an older source head;
- the diff changes after the base/head proof or final AI-review receipt;
- a new required check or unresolved material review thread appears;
- evidence digests no longer match; or
- blocking follow-up remains open.

Revalidation updates the report; it never rewrites old evidence as if it came
from the new head.

## Unraid repository conventions

Re-read the live repository instructions for every PR; the notes here are a
prompt, not a frozen substitute.

For `unraid/core`:

- Canonical implementation work belongs in `core/worktrees/<task-slug>`, not
  the read-only canonical checkout.
- Default task branches follow `<prefix>/<lane>-<task-slug>`; `codex/` is the
  established agent-neutral default. Record the selected lane.
- Record Linear attachment or explicit skip reasoning, the AI review marker
  forecast/final receipt and reviewed SHA, release/Knōpe impact, scoped checks,
  full `mix quality` status, browser/QA/E2E evidence where applicable, and the
  separate `./scripts/check_before_push.sh` result.
- Product docs and E2E may belong in `unraid/unraid8-docs` and
  `unraid/unraid-e2e`; say whether companion work is required.

For `unraid/core-plugins`:

- Canonical implementation work belongs in
  `core-plugins/worktrees/<task-slug>`, not `core-plugins/main`.
- Map plugin source under `priv/plugins/<plugin-id>`, plugin tests under
  `test/plugins/<plugin-id>`, and the reusable harness under `test/support`.
- Record `$SKILL_DIR/references/runtime/scripts/test.sh` results using the runtime pinned by
  `build_deps.json`, Linear attachment or skip reasoning, AI review marker
  state, package build evidence, and release-please/conventional-commit impact.
  Conventional commits scoped to a plugin drive its release; list every commit
  subject and explain its release effect.

For every Unraid organization repository, verify the exact live repository
identity and current instructions before reporting readiness. This artifact
never grants permission to push, create/update a PR, comment, or publish an
artifact. Those actions require explicit current-request authorization.

## Evidence discipline

Every substantive claim must include a stable claim ID, observation,
reproduction, exact evidence IDs,
sources, and a boundary. Commands include cwd, relevant non-secret environment,
exit status, and verbatim output. Preserve failures rather than cleaning the
record. When output is long, retain it in a durable evidence file, give its
absolute path and digest, and quote only the decisive excerpt.

Only captured local files enter the evidence manifest. A pinned URL remains a
reference until its exact bytes are captured locally. Prefer
`$SKILL_DIR/references/runtime/scripts/capture-pr-evidence.py` for commands; it never invokes a shell and
records argv, cwd, duration, exit status, stdout, stderr, timestamp, and only
explicitly allowlisted non-secret environment fields. Synchronize manifest rows
with `$SKILL_DIR/references/runtime/scripts/sync-pr-report-ledgers.py`, then validate and seal again.

The authoring template may reference packaged local fonts for visual parity in
this repository. Anything claimed to be portable or offline must be produced
with the public `export --out NEW_DIRECTORY` command and checked as that export.

The proof package must distinguish:

- source/code-path evidence from runtime evidence;
- focused checks from integrated checks;
- locally run checks from CI/QA checks;
- current-head results from earlier results;
- branch-caused failures from pre-existing or environmental failures;
- observed facts from inference and recommendations;
- “not applicable,” “not run,” “blocked,” and “passed.”

Use “independently reproducible, falsifiable, exact-base/exact-head comparative
proof with declared boundaries,” not “irrefutable.” Software evidence proves a
bounded claim; it does not eliminate every possible environment or future state.

For stateful proof, include the complete resource ledger: identities, data roots,
ports, processes, listeners, credentials, files, accounts, creation, teardown,
cleanup errors, retained evidence, and an external zero-residual check.

## Canonical does not mean duplicated

The PR report is the top-level map and canonical index for the PR. Large raw
logs, test captures, plans, specs, reports, session deep dives, and durable docs
remain in their owned artifacts. Link them with `artifact.related`, summarize
their decisive facts here, pin versions, and record integrity hashes when the
source may change. Do not paste the same mutable fact into several places
without naming which source owns it.

## Public/private boundary

Absolute worktree paths, transcript paths, machine names, local accounts,
private URLs, internal infrastructure, and session identifiers can be required
inside this private report while being forbidden in a public repository. Before
anything is copied to a public PR, independently scan branch names, commit
messages, diff contents, PR title/body, comments, logs, screenshots, and linked
artifacts for secrets, PII, local paths, hostnames, private IPs, tokens, and
internal-only product naming. Record the audit and authorization; never assume
that report completeness implies publication safety.

## Before calling a report current

1. Re-resolve repository, base/head, merge base, worktree, PR, and CI state.
2. Re-run or timestamp every decisive verification against the current head.
3. Confirm each touched file, commit, package/version delta, and generated file.
4. Reconcile open review threads, findings, required docs, and follow-up work.
5. Verify transcript paths and related artifact links resolve.
6. Verify every evidence digest and reseal the normalized report digest.
7. Exercise artifact accessibility and portable export.
8. Run the package checks:

```bash
python3 "$SKILL_DIR/scripts/artifacts.py" validate --path "$REPORT"
python3 "$SKILL_DIR/scripts/artifacts.py" index
```

Use `draft` while facts are incomplete, `review` when evidence is ready for
challenge, `accepted` only when the committed PR state and all required proof
are current, and `superseded` when another report names the successor.

## Reviewer-control interface

The canonical layout is a six-stage reviewer route: Orient, Change, Prove,
Review, Operate, and Handoff. Preserve all 29 governed sections and their stable
IDs when changing presentation. Apply structural updates through
`$SKILL_DIR/references/runtime/scripts/redesign-pr-report-layout.py`; it fails closed on a missing or extra
section and resets integrity seals for deliberate regeneration.

The interface derives posture, section badges, stage aggregates, unresolved and
post-review filters, freshness warnings, executive diff counts, evidence
backlinks, and review deltas from existing governed states and authoritative
ledgers. Never hand-maintain a decorative duplicate of those facts. Public
preview is a local visibility aid only: it exposes the audited public-summary
surface, does not sanitize or export the underlying private HTML, and is never
publication authorization.

## Declarative evidence system

`$SKILL_DIR/references/runtime/pr-reports/schema/sections.json` is the authoritative six-stage, 29-section denominator.
The template, validator, machine manifest, reviewer navigation, readiness matrix,
and skill must agree with it. Do not add or remove a governed section only in HTML.

Run `python3 "$SKILL_DIR/scripts/artifacts.py" pr compile "$REPORT"` after material report changes. It embeds
a canonical `application/json` machine manifest containing identity, section
states, stable claims, evidence types and digests, claim-to-evidence edges,
review acknowledgements, graph defects, and explicit readiness denominators.

Every decisive claim must trace through a stable claim ID to evidence. Treat a
dangling reference, unsupported claim, unused decisive evidence item, conflicting
record, or current-head mismatch as a report defect. Classify evidence as an
immutable snapshot, reproducible command, human observation, inference, live
reference, or unverified assertion. A mutable URL alone is not decisive proof.

Review acknowledgements created by `pr-report.py acknowledge` bind the reviewer,
checkpoint, timestamp, exact head SHA, and report SHA-256. A material report-byte
or head change makes an earlier acknowledgement stale.

Use `pr-report.py bundle` for a portable hash-manifested evidence package,
`pr-report.py diff` for field-level review deltas, and `pr-report.py
export-public` for a fail-closed sanitized candidate. Public export generation
never grants publication authority and still requires a human destination and
payload audit.

Use `pr-report.py watch-evidence -- --branch BRANCH ...` or `--worktree PATH`
to capture a Cortex historical plus live evidence stream. The stream must be
branch/worktree scoped, resumable from its opaque cursor, content-scrubbed by
Cortex, bounded, and imported into the evidence manifest like any other durable
file. A stream is lifecycle evidence; it does not automatically prove a claim.

Resolve all advanced helpers above from the installed `SKILL_DIR`. Use absolute
report paths and set `ARTIFACTS_ROOT` for a non-default output root. The target
repository commands in the Unraid-specific section are run from that repository,
not from the skill or output directory.
