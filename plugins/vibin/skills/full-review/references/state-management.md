# Session State, Scope Freezing, and Recovery

Read this reference before creating, updating, archiving, or resuming `.full-review/` artifacts.

## Paths and safe archival

Resolve the root with `git rev-parse --show-toplevel`, falling back to `pwd` only outside Git.

- Active session: `<root>/.full-review/`
- Prior sessions: `<root>/.full-review-archive/<UTC timestamp>-<short SHA>/` in Git, or `<UTC timestamp>-nogit-<first 12 characters of scope_sha256>/` outside Git

The archive is a sibling, never a child of the directory being archived. Refuse an existing destination. Rename the active directory on the same filesystem. If rename is unavailable, copy to a temporary sibling, verify file counts and checksums, rename the verified copy, and only then remove the original. Never overwrite or delete an older archive.

## Frozen target

Before writing review artifacts, capture repository root, VCS mode, branch, reviewed commit, diff base, porcelain status, immutable patch and SHA-256, eligible and changed-file lists, and scoped hashes for tracked and eligible untracked files. The frozen dirty evidence includes committed-base changes, staged changes, unstaged changes, deletions, renames, and eligible untracked files. For every eligible untracked file, record path, `kind: untracked`, mode when relevant, byte size, SHA-256, and a reference to its checksummed immutable copy under `.full-review/scope-files/`; register every frozen copy and checksum in `artifacts.json`. Reviewers consume frozen copies, never mutable untracked paths. Exclude `.full-review/**`, `.full-review-archive/**`, ignored, generated, vendored, binary, and unsupported files unless explicitly targeted. Record `scope_mode` as `diff` or `snapshot`.

Outside Git, set `vcs` to `none`, `reviewed_commit`, `diff_base`, and `patch_sha256` to `null`, and `scope_mode` to `snapshot`; freeze every eligible target file with a complete content-hash manifest. In Git, set `vcs` to `git` and use the applicable commit and diff boundary. Scope and report metadata always show VCS mode and must not claim a commit or diff when `vcs` is `none`.

Write immutable target evidence to `scope.json`. Write mutable assignment and inspection status to `coverage.json`. Reviewers consume `scope.json` and never recompute a mutable diff. Only `scope.json` supplies `scope_sha256`.

## State machine

Use one enumerated status:

```text
scope → phase_1 → phase_2 → checkpoint_1 → phase_3 → phase_4
      → checkpoint_2 → phase_5 → complete
```

Exceptional states:

- `failed`: record `failed_step` and `last_error`; preserve artifacts.
- `partial`: user explicitly accepted skipped/failed reviewers and requested a partial report.
- `superseded`: the target changed, including authorized fixes at a checkpoint.

Track partial execution separately with `result_mode`: `complete` by default and
`partial` after the user authorizes any failed or skipped reviewer. Intermediate
execution always uses the normal enumerated phase and checkpoint statuses; a
session whose `result_mode` is `partial` may terminate only with status `partial`.

Stable completed-step IDs are `scope`, `quality`, `architecture`, `security`, `performance`, `testing`, `documentation`, `framework`, `operations`, and `consolidation`.

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

`artifacts.json` records `path`, `kind`, `status`, `sha256`, `created_at`, and optional reviewer for immutable scope, raw, consolidated, and final-report artifacts. `state.json`, `coverage.json`, and `artifacts.json` are mutable controller documents and are not checksummed inside the manifest; `artifacts.json` never contains its own checksum. A terminal detached manifest snapshot may seal controller integrity when needed.

## Atomic updates

Write state and manifest changes to sibling temporary files, flush and close, then atomically rename. Update in this order: write and verify the phase artifact; add its checksum to `artifacts.json`; update coverage; transition `state.json`. Never transition before required artifacts are durable.

## Resume and invalidation

Verify artifacts and target fingerprints before resuming.

- Resume `scope` or `phase_N` at the first incomplete step.
- At `checkpoint_N`, present the checkpoint without repeating completed reviewers.
- For `failed`, ask to retry, explicitly skip for a partial report, or archive. On authorized skip, write and register a raw placeholder containing reviewer, partition, failed step, error, attempted evidence, timestamp, and user authorization; record it as `failed` or `skipped`, append the diagnostics to `failure_history`, clear the current `failed_step` and `last_error`, set `result_mode` to `partial`, and return to the next normal resumable phase or checkpoint based on completed steps and registered placeholders. Continue requested phases and finish only with status `partial`.
- Never append to `partial`, `complete`, or `superseded`; archive and start fresh.

If any target fingerprint differs, mark the session `superseded`. Authorized fixes happen outside the session and require a new frozen review.
