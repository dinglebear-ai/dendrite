# Session State, Scope Freezing, and Recovery

Read this reference before creating, updating, archiving, or resuming `.full-review/` artifacts.

## Paths and transient scratch

Resolve the root with `git rev-parse --show-toplevel`, falling back to `pwd` only outside Git.

- Active session: `<root>/.full-review/`
- Failed or interrupted session: keep `<root>/.full-review/` in place for recovery
- Prior terminal or mismatched sessions: `<root>/.full-review-archive/<UTC timestamp>-<short SHA>/` in Git, or `<UTC timestamp>-nogit-<scope digest prefix>/` outside Git

Resume a matching incomplete session in place. Move a terminal or mismatched session into the exact archive tree above with a same-filesystem atomic rename and refuse collisions. The current successful session must not be archived as a normal completion path.

## Frozen target

Before writing review artifacts, capture repository root, VCS mode, branch, reviewed commit, diff base, porcelain status, immutable patch and SHA-256, eligible and changed-file lists, and scoped hashes for tracked and eligible untracked files. The frozen dirty evidence includes committed-base changes, staged changes, unstaged changes, deletions, renames, and eligible untracked files. For every eligible untracked file, record path, `kind: untracked`, mode when relevant, byte size, SHA-256, and a reference to its checksummed immutable copy under `.full-review/scope-files/`; register every frozen copy and checksum in `artifacts.json`. Reviewers consume frozen copies, never mutable untracked paths. Exclude `.full-review/**`, `.full-review-archive/**`, ignored, generated, vendored, binary, and unsupported files unless explicitly targeted. Record `scope_mode` as `diff` or `snapshot`.

In diff mode, store the exact combined committed-base, staged, unstaged, rename, and deletion evidence at `.full-review/scope.patch`, register its checksum, and set `patch_path` in `scope.json`. Eligible untracked files remain checksummed immutable copies because Git patches cannot carry their full provenance reliably.

Outside Git, set `vcs` to `none`, `reviewed_commit`, `diff_base`, and `patch_sha256` to `null`, and `scope_mode` to `snapshot`; freeze every eligible target file with a complete content-hash manifest. In Git, set `vcs` to `git` and use the applicable commit and diff boundary. Scope and report metadata always show VCS mode and must not claim a commit or diff when `vcs` is `none`.

Write immutable target evidence to `scope.json`. Create a separate immutable contextual-evidence manifest for checksummed callers, shared contracts, lockfiles, CI, deployment configuration, and captured read-only command output needed by the assigned dimensions. Store contextual files under `.full-review/context-files/`; record path, revision, hash, purpose, and target-versus-context classification. Write mutable assignment and inspection status to `coverage.json`. Reviewers never recompute a mutable diff.

## State machine

Use one enumerated status:

```text
scope → phase_1 → phase_2 → phase_3 → phase_4 → consolidation
      → artifact_creation → evidence_sealing → artifact_validation
      → ready_for_cleanup
```

Exceptional states:

- `failed`: record `failed_step` and `last_error`; preserve artifacts.
- `superseded`: the target changed before the final artifact was created.

Track partial execution separately with `result_mode`: `complete` by default and
`partial` when a required reviewer or evidence source cannot be completed after
safe retry or fallback. Continue the batch through consolidation so the artifact
accounts for the limitation; never silently omit it or call the result complete.

Stable completed-step IDs are `scope`, `quality`, `architecture`, `security`, `performance`, `testing`, `documentation`, `framework`, `operations`, `consolidation`, `artifact_creation`, `evidence_sealing`, `artifact_validation`, and `ready_for_cleanup`. `result_mode`, not `status`, records `complete` versus `partial` coverage.

## State document

```json
{
  "schema_version": 1,
  "status": "scope",
  "result_mode": "complete",
  "target": "description",
  "vcs": "git-or-none",
  "reviewed_commit": "sha-or-null",
  "diff_base": "sha-or-null",
  "patch_sha256": "digest-or-null",
  "scope_manifest": ".full-review/scope.json",
  "scope_sha256": "digest",
  "flags": {
    "security_focus": false,
    "performance_critical": false,
    "strict_mode": false,
    "framework": null
  },
  "completed_steps": [],
  "failed_step": null,
  "last_error": null,
  "failure_history": [],
  "artifact_manifest": ".full-review/artifacts.json",
  "started_at": "ISO-8601",
  "last_updated": "ISO-8601"
}
```

`artifacts.json` records `path`, `kind`, `status`, `sha256`, `created_at`, and optional reviewer for immutable scope, raw, and consolidated scratch artifacts. Its `final_artifact` object records artifact path, repository identity, final SHA-256, evidence-bundle path, seal and verification receipts, final validation command/exit/timestamp/verbatim output, index command/exit/timestamp/verbatim output, and the lookup proving the intended artifact card appears in the index. The final report embeds the seal and verification receipts so they survive scratch cleanup. `state.json`, `coverage.json`, and `artifacts.json` are mutable controller documents and are not checksummed inside the manifest.

## Atomic updates

Write state and manifest changes to sibling temporary files, flush and close, then atomically rename. Update in this order: write and verify the phase artifact; add its checksum to `artifacts.json`; update coverage; transition `state.json`. Never transition before required artifacts are durable.

## Resume and invalidation

Verify artifacts and target fingerprints before resuming.

- Resume `scope` or `phase_N` at the first incomplete step.
- There are no phase checkpoints. Resume at the first incomplete step and continue through delivery without asking whether to proceed.
- For a failed reviewer, record each attempt in `failure_history`, retry safely, or use an available equivalent reviewer without leaving the current phase. If evidence remains unavailable, write and register a raw placeholder containing reviewer, partition, failed step, error, attempted evidence, and timestamp; set `result_mode` to `partial` and continue. Use terminal `failed` only when a valid, indexed artifact and verified evidence bundle cannot be delivered.
- Never append to `failed`, `ready_for_cleanup`, or `superseded`; archive and start fresh.

If any target fingerprint differs, mark the session `superseded`. Authorized fixes happen outside the session and require a new frozen review.
