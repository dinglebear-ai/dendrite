---
type: Automation Overview
title: CI/CD and Scripts
description: GitHub Actions workflows, pre-push hooks, and maintenance scripts that validate, synchronize, and test the Dendrite marketplace.
tags: [ci-cd, automation, workflows, scripts, validation, github-actions]
---

# CI/CD and Scripts

Dendrite uses GitHub Actions workflows and shell scripts to validate, synchronize, and test the marketplace across both `main` and `marketplace-no-mcp` branches.

## GitHub Actions Workflows

### OpenWiki Update

**File:** [`.github/workflows/openwiki-update.yml`](.github/workflows/openwiki-update.yml)

**Triggers:**
- Manual workflow dispatch
- Daily schedule (08:00 UTC)

**Purpose:** Regenerates the OpenWiki documentation and creates a pull request.

**Steps:**
1. Checks out repository
2. Sets up Node.js
3. Installs OpenWiki globally
4. Runs `openwiki --update --print`
5. Creates a PR against `openwiki/update` branch if changes were made

**Environment:**
- `OPENWIKI_PROVIDER`: anthropic
- `ANTHROPIC_API_KEY`: GitHub secret
- `ANTHROPIC_BASE_URL`: GitHub secret
- `OPENWIKI_MODEL_ID`: claude-opus-4.8

### Sync Marketplace No-MCP

**File:** [`.github/workflows/sync-marketplace-no-mcp.yml`](.github/workflows/sync-marketplace-no-mcp.yml)

**Triggers:**
- Push to `main`
- Daily schedule (08:00 UTC)
- Manual workflow dispatch

**Purpose:** Keeps the `marketplace-no-mcp` branch synchronized with `main` by applying the no-MCP transform.

**Steps:**
1. Checks out `main`
2. Sets up Node.js
3. Runs `plugins/scripts/apply-no-mcp-marketplace`
4. Validates both marketplace manifests
5. Runs the no-MCP invariant check
6. Pushes `marketplace-no-mcp` if changed

**Transform Process:**
- Takes `main`'s tree wholesale (`git read-tree --reset -u origin/main`)
- Removes all `.mcp.json` files
- Strips `mcpServers` entries from `gemini-extension.json` files
- Regenerates README inventory and generated docs
- Validates manifests and invariants
- Pushes only when the transform produces a change

See [marketplace model](marketplace-model.md) for details.

### Check No-MCP Drift

**File:** [`.github/workflows/check-no-mcp-drift.yml`](.github/workflows/check-no-mcp-drift.yml)

**Triggers:**
- Daily schedule
- Manual workflow dispatch

**Purpose:** Compares `origin/marketplace-no-mcp` with `origin/main` plus the deterministic no-MCP transform.

**Steps:**
1. Checks out repository
2. Fetches `origin/main` and `origin/marketplace-no-mcp`
3. Runs `plugins/scripts/check-no-mcp-drift --compare-ref`
4. Smoke-tests marketplace installs from both refs
5. Reports drift or validation failures

You can run the same check locally:
```bash
plugins/scripts/check-no-mcp-drift --compare-ref
```

### Validate Marketplaces

**File:** [`.github/workflows/validate-marketplaces.yml`](.github/workflows/validate-marketplaces.yml)

**Triggers:**
- Push to any branch
- Pull request to any branch

**Purpose:** Validates marketplace manifests on every push and PR.

**Checks:**
- Claude marketplace manifest JSON parsing
- Codex marketplace manifest JSON parsing
- Plugin manifest alignment (Claude/Codex/Gemini)
- Skill companion presence (every `SKILL.md` has `openai.yaml`)
- Plugin documentation presence (non-empty README/CHANGELOG)
- Upstream sources schema validation
- Generated docs consistency

## Pre-Push Hook

**File:** [`.githooks/pre-push`](.githooks/pre-push)

**Purpose:** Validates repository state before pushing.

**Checks:**

1. **No Labby plugin copy:**
   ```bash
   test ! -e plugins/labby
   ```
   Labby plugin lives in `jmagar/lab` and is referenced as a marketplace entry, not carried locally.

2. **No-MCP drift (scoped to main and marketplace-no-mcp pushes):**
   ```bash
   plugins/scripts/check-no-mcp-drift --compare-ref
   ```
   Feature-branch pushes are not blocked by pre-existing cross-ref drift.

3. **Plugin documentation:**
   ```bash
   plugins/scripts/check-plugin-docs
   ```
   Ensures all plugins have non-empty README and CHANGELOG files.

4. **Marketplace alignment:**
   ```bash
   plugins/scripts/check-marketplace-sync
   ```
   Ensures Claude and Codex marketplace entries are aligned.

5. **Manifest parsing:**
   ```bash
   jq empty .claude-plugin/marketplace.json
   jq empty .agents/plugins/marketplace.json
   ```

**Enable the hook:**
```bash
git config core.hooksPath .githooks
```

## Maintenance Scripts

All scripts live under `/plugins/scripts/`.

### Validation Scripts

**`check-all`**
- Runs comprehensive validation suite
- Checks marketplace manifest alignment
- Validates skill companion presence
- Checks plugin documentation
- Validates upstream sources schema
- Validates generated docs consistency

**`check-plugin-docs`**
- Rejects empty plugin README/CHANGELOG placeholders
- Ensures every plugin has useful documentation

**`check-marketplace-sync`**
- Ensures Claude and Codex marketplace entries are aligned
- Normalizes source targets and compares plugin names

**`check-no-mcp-drift`**
- Compares `marketplace-no-mcp` with `main` plus no-MCP transform
- Accepts `--compare-ref` flag for CI-friendly drift detection
- Smoke-tests marketplace installs when invoked

**`validate-plugin-schemas`**
- Validates plugin manifests against schemas
- Validates upstream sources JSON against schema
- Validates Gemini extension manifests

**`audit-upstream-schema-sources`**
- Prints upstream docs/source files for Codex and Gemini schemas
- Use this before changing `plugins/schemas/*`

### Generation Scripts

**`generate-gemini-extensions`**
- Regenerates `gemini-extension.json` files from plugin metadata
- Uses plugin manifest data, user config, and MCP snippets
- Ensures Gemini extensions stay aligned with Claude/Codex manifests

**`generate-readme-inventory`**
- Regenerates the README inventory table
- Counts plugins, skills, MCP servers, OpenAI agents, and commands
- Updates the generated inventory section

**`generate-docs`**
- Regenerates all generated documentation:
  - `docs/plugin-matrix.md`
  - `docs/configuration-matrix.md`
  - `docs/marketplace-sources.md`
  - `docs/schema-provenance.md`
  - `docs/no-mcp-variant.md`

### Transform Scripts

**`apply-no-mcp-marketplace`**
- Applies the no-MCP transform to the current working tree
- Removes `.mcp.json` files
- Strips `mcpServers` from Gemini manifests
- Regenerates README and generated docs
- Used by the sync workflow to maintain `marketplace-no-mcp`

**`sync-upstream-skills`**
- Onboards new upstream skills from GitHub folder URLs
- Checks drift for vendored skills
- Applies updates from upstream sources
- See [vendored upstream skills](vendored-upstream-skills.md)

### Test Scripts

**`smoke-marketplace-install`**
- Smoke-tests Claude, Codex, and Gemini marketplace/extension installs
- Uses temporary home directories to avoid affecting local installs
- Validates that marketplace entries install correctly

**`health-check`**
- Runs basic health checks on the repository
- Validates executable bits on scripts
- Checks for common issues

### Utility Scripts

**`link-claude-mds`**
- Ensures AGENTS.md and GEMINI.md are symlinks to CLAUDE.md
- Maintains the single-source-of-truth pattern

**`refresh-javy-plugin.sh`**
- Refreshes the Javy plugin from its upstream source

**`generate-gemini-extensions`**
- Regenerates Gemini extension manifests from plugin metadata

**`protected-mcp-smoke`**
- Smoke-tests protected MCP servers

**`cleanup-leaked-mcp.sh`**
- Cleans up leaked MCP server registrations

**`apply-no-mcp-marketplace`**
- Applies the no-MCP transform locally for testing

**`acp-smoke-check`**
- Smoke test for ACP plugin

## Schema Files

Schema definitions live under `/plugins/schemas/`:

- **`codex-plugin.schema.json`**: Codex plugin manifest schema
- **`gemini-extension.schema.json`**: Gemini extension manifest schema
- **`upstream-sources.schema.json`**: Upstream sources manifest schema
- **`codex-marketplace.schema.json`**: Codex marketplace manifest schema

These schemas validate generated and hand-written manifests to ensure consistency.

## Script Execution Patterns

### Common Workflow

After changing marketplace entries, plugin manifests, or upstream skills:

```bash
# 1. Regenerate generated files
plugins/scripts/generate-gemini-extensions
plugins/scripts/generate-readme-inventory
plugins/scripts/generate-docs

# 2. Validate everything
plugins/scripts/check-all

# 3. Check no-MCP drift
plugins/scripts/check-no-mcp-drift --compare-ref

# 4. Smoke-test installs
plugins/scripts/smoke-marketplace-install
```

### Upstream Skill Sync

```bash
# 1. Check for drift
plugins/scripts/sync-upstream-skills check

# 2. Apply updates if needed
plugins/scripts/sync-upstream-skills apply --all

# 3. Validate
plugins/scripts/check-all

# 4. Review and commit
git diff
git commit
```

### No-MCP Transform

```bash
# Apply the transform locally to test
plugins/scripts/apply-no-mcp-marketplace

# Review the changes
git diff

# Reset if needed
git reset --hard HEAD
```

## Related Documentation

- [Marketplace Model](marketplace-model.md): Dual-branch architecture and sync workflow
- [Operations](operations.md): Common maintenance workflows
- [Plugin Structure](plugin-structure.md): Plugin manifests and validation requirements
