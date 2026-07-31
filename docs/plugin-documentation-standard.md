---
title: Plugin documentation standard
created: 2026-07-30
updated: 2026-07-30
---

# Plugin Documentation Standard

Every plugin with skills or Claude/Codex manifests must include useful
`README.md` and `CHANGELOG.md` files. Empty placeholders are not acceptable.

## README Minimum

A plugin README should include:

- What the plugin operates or enables.
- What skills, commands, hooks, MCP servers, or scripts it ships.
- Configuration keys and where generated config files are written.
- A safe verification command.
- Any destructive-operation or credential handling cautions.

Keep plugin READMEs concise. Put detailed operational recipes in the skill body
or a plugin-local `docs/` file when the workflow is large.

## CHANGELOG Minimum

A plugin changelog should include:

- `# Changelog`
- `## Unreleased`
- Bullets for notable additions, changes, fixes, and removals.

Use plugin changelogs for plugin-local behavior and root `CHANGELOG.md` for
repo-wide marketplace, CI, schema, generated-doc, and release-process changes.

## Enforcement

`plugins/scripts/check-plugin-docs` fails when a plugin README or CHANGELOG is
missing or has fewer than three nonblank lines. `plugins/scripts/check-all`
runs that check.
