---
type: Operations Workflow
title: Marketplace Operations
description: Common workflows for adding, updating, and removing marketplace plugins and entries, including validation checks and smoke testing.
tags: [operations, workflows, plugins, marketplace, validation]
---

# Marketplace Operations

This page documents common workflows for maintaining the Dendrite marketplace. Use it when adding, removing, renaming, or updating marketplace entries.

## Source Model

- **`main`**: Full/default marketplace, may include local `.mcp.json` files and Gemini `mcpServers` entries
- **`marketplace-no-mcp`**: Generated from `main` for installs that don't want bundled MCP registrations
- **External sources**: Referenced from marketplace manifests instead of copied into this repository

See [marketplace model](marketplace-model.md) for architecture details.

## Add a Local Plugin

### 1. Create Plugin Structure

Put source under `/plugins/<name>/` with the standard layout:

```bash
plugins/<name>/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── gemini-extension.json
├── skills/
│   └── <skill>/
│       ├── SKILL.md
│       ├── agents/
│       │   └── openai.yaml
│       ├── README.md
│       └── CHANGELOG.md
├── README.md
└── CHANGELOG.md
```

See [plugin structure](plugin-structure.md) for the complete layout and requirements.

### 2. Add Marketplace Entries

Add matching entries to both marketplace manifests:

- `.claude-plugin/marketplace.json`
- `.agents/plugins/marketplace.json`

Keep entries normalized to the same plugin name and source target.

```json
{
  "name": "my-plugin",
  "source": "./plugins/my-plugin",
  "description": "Plugin description"
}
```

### 3. Generate and Validate

Run the full generation and validation pipeline:

```bash
# Regenerate Gemini manifests from plugin metadata
plugins/scripts/generate-gemini-extensions

# Regenerate README inventory and generated docs
plugins/scripts/generate-readme-inventory
plugins/scripts/generate-docs

# Run all validation checks
plugins/scripts/check-all

# Smoke-test marketplace installs
plugins/scripts/smoke-marketplace-install
```

### 4. Review and Commit

Review `git diff` for:
- Marketplace manifest changes
- Generated Gemini extensions
- README inventory updates
- Generated documentation updates

Commit when satisfied.

## Add a Curated Remote Plugin

### 1. Choose Source Type

Prefer `git-subdir` when the plugin lives below a repository subdirectory:

```json
{
  "name": "remote-plugin",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/owner/repo.git",
    "path": "plugins/plugin-name",
    "ref": "main",
    "sha": "commit-sha"
  }
}
```

Pin external third-party plugins by `sha` when practical.

### 2. Add to Both Marketplaces

Keep Claude and Codex entries normalized to the same `repo`, `path`, `ref`, and `sha`.

### 3. Regenerate Docs

Update documentation by running:

```bash
plugins/scripts/generate-docs
```

This refreshes `docs/marketplace-sources.md` and other generated documentation.

### 4. Validate

```bash
plugins/scripts/check-all
```

## Update Plugin Metadata

### 1. Update Manifests

Edit plugin manifests as needed:

- `.claude-plugin/plugin.json`
- `.codex-plugin/plugin.json`
- `gemini-extension.json`
- `.mcp.json` (if present)

### 2. Regenerate Generated Files

```bash
plugins/scripts/generate-gemini-extensions
plugins/scripts/generate-readme-inventory
plugins/scripts/generate-docs
```

### 3. Validate

```bash
plugins/scripts/check-all
plugins/scripts/smoke-marketplace-install
```

## Remove a Plugin

### 1. Remove Marketplace Entries

Remove the plugin from both manifests:

- `.claude-plugin/marketplace.json`
- `.agents/plugins/marketplace.json`

### 2. Remove Local Plugin Directory

If Dendrite owns the plugin (source is `./plugins/<name>`), remove the directory:

```bash
rm -rf plugins/<name>
```

### 3. Update No-MCP Configuration

If the plugin name is in `NO_MCP_REF_NAMES` in [`plugins/scripts/apply-no-mcp-marketplace`](plugins/scripts/apply-no-mcp-marketplace), remove it.

### 4. Regenerate and Validate

```bash
plugins/scripts/generate-gemini-extensions
plugins/scripts/generate-readme-inventory
plugins/scripts/generate-docs
plugins/scripts/check-all
plugins/scripts/smoke-marketplace-install
```

## MCP-Backed Entries

### For the Full Marketplace

Keep MCP registrations where they are useful for a normal user. Include `.mcp.json` files in the plugin directory and `mcpServers` entries in `gemini-extension.json`.

### For the No-MCP Variant

Add the plugin name to `NO_MCP_REF_NAMES` in [`plugins/scripts/apply-no-mcp-marketplace`](plugins/scripts/apply-no-mcp-marketplace) **only when** that remote plugin also has a `marketplace-no-mcp` ref.

This tells the transform to use the no-MCP ref instead of attempting to strip MCP config.

**Never hand-edit `marketplace-no-mcp` as the primary fix.** Change `main` and the transform, then let the sync workflow publish the derived branch.

See [marketplace model](marketplace-model.md) for details.

## Sync Upstream Skills

### Check Drift

```bash
plugins/scripts/sync-upstream-skills check
```

Reports whether vendored skills have drifted from their upstream sources.

### Apply Updates

```bash
plugins/scripts/sync-upstream-skills apply --all
```

Pulls updates from upstream. Review `git diff` and commit.

See [vendored upstream skills](vendored-upstream-skills.md) for the complete workflow.

## Required Checks

Before pushing changes, run these checks:

```bash
# Full validation suite
plugins/scripts/check-all

# Compare marketplace-no-mcp with main + transform
plugins/scripts/check-no-mcp-drift --compare-ref

# Smoke-test marketplace installs
plugins/scripts/smoke-marketplace-install
```

## Pre-Push Hook

Enable the tracked pre-push hook in a clone:

```bash
git config core.hooksPath .githooks
```

The pre-push hook validates:
- No `plugins/labby` directory (Labby plugin lives in `jmagar/lab`)
- Marketplace manifest JSON parsing
- Plugin documentation presence
- Marketplace entry alignment
- No-MCP drift for pushes to `main` or `marketplace-no-mcp`

Feature-branch pushes are not gated by pre-existing cross-ref drift.

## Related Documentation

- [Marketplace Model](marketplace-model.md): Dual-branch architecture and no-MCP variant
- [Plugin Structure](plugin-structure.md): Standard plugin layout and requirements
- [Vendored Upstream Skills](vendored-upstream-skills.md): Upstream skill synchronization
- [Automation](automation.md): CI/CD workflows and maintenance scripts
