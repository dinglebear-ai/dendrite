# Changelog

## Unreleased

- Removed protected-long-lived-ref handling from `repo-status`, including the
  `protected_long_lived_ref` status value. It only ever described the
  `marketplace-no-mcp` marketplace variant, which has been retired.
- Added `review-pr` so Codex can run the PR Review Toolkit command flow as a
  Vibin skill, including code, tests, comments, silent failures, type design,
  and simplification passes.
- Added `merge-status` for read-only merge readiness checks across dirty state,
  mergeability, branch/worktree overlap, lint/tests/CI, docs, and config
  example drift.
- Updated `work-it` to reuse safe existing worktrees, route creation through
  `worktree-setup`, copy plans into the worktree, open an early draft PR,
  invoke `review-pr` for the mandatory PR review sweep, require mandatory review
  waves, commit early/often, and finish through `quick-push`.
- Reinforced `quick-push` session logging so repeat pushes update an existing
  session log only when there is substantive new information.
- Removed the `summarize` skill from Vibin.
- Removed the duplicate `yt-dlp` skill because the dedicated `ytdl-mcp` marketplace plugin now owns that capability.
- Restored `create-swag-config` to Vibin with variableized SWAG deployment settings after removing the retired standalone `swag-mcp` marketplace entry.
- Removed the `mcp-gateway-tools` skill from Vibin.
- Skill quality pass: fixed the `paperless-ngx` `$SKILL_DIR` script-path bug and stale `.env` guidance, strengthened the `fastmcp-client-cli` description and cleaned placeholder metadata, added a required-vs-optional dependency preamble to `work-it`, clarified `<skill-dir>` resolution in `monolith-check`, and scoped `refresh-docs` to its host pipeline.

## 0.1.0

- Initial Vibin plugin scaffold with quick-push and save-to-md skills.
