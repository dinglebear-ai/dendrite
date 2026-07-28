# Changelog

All notable changes to the `repo-status` skill are recorded here.

## 2026-07-28

### Removed

- Removed the protected-long-lived-ref handling entirely: the `## Protected Long-Lived Refs` section, the `protected_long_lived_ref` status value, and the related clauses in per-branch review, merge order, and the final report shape. The only ref it ever described was `marketplace-no-mcp`, and that marketplace variant has been retired. Branches are now classified purely on live Git, PR, and CI evidence.

## 2026-06-18

### Changed

- Added explicit `marketplace-no-mcp` handling as a protected long-lived marketplace variant so repo-status reports it as intentionally preserved and avoids merge/cleanup recommendations.

## 2026-06-15

### Added

- Added packaging documentation so the skill has a README and changelog alongside `SKILL.md`.
