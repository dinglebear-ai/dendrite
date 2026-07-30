---
title: Release and changelog policy
created: 2026-07-30
updated: 2026-07-30
---

# Release And Changelog Policy

Dendrite currently tracks changes under an `Unreleased` section. Keep root and
plugin changelogs current so marketplace behavior can be audited without reading
commit history.

## Root Changelog

Update `CHANGELOG.md` for repo-wide changes:

- Marketplace entry additions, removals, and source/ref policy changes.
- CI, schema, and install-smoke automation.
- Generated documentation behavior.
- Cross-plugin documentation or configuration contract changes.

## Plugin Changelogs

Update `plugins/<name>/CHANGELOG.md` for plugin-local behavior:

- New or changed skills.
- New commands, hooks, MCP server snippets, or setup scripts.
- UserConfig changes.
- Important fixes or safety policy changes.

## Before Publishing

Run:

```bash
plugins/scripts/check-all
plugins/scripts/smoke-marketplace-install
```
