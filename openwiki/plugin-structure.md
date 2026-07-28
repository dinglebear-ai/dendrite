---
type: Structural Standard
title: Plugin Structure
description: Standard Dendrite plugin layout including required manifests, skills, MCP registrations, commands, hooks, and companion files.
tags: [plugins, structure, manifests, skills, mcp, commands, hooks]
---

# Plugin Structure

Dendrite plugins follow a consistent layout that works across Claude Code, Codex, and Gemini runtimes. This structure enables portable marketplace installations while supporting runtime-specific features.

## Standard Plugin Layout

A typical Dendrite plugin lives under `/plugins/<name>/` with this structure:

```
plugins/<name>/
├── .claude-plugin/
│   └── plugin.json          # Claude plugin manifest
├── .codex-plugin/
│   └── plugin.json          # Codex plugin manifest
├── gemini-extension.json    # Gemini extension manifest (required if Claude/Codex manifests exist)
├── .mcp.json                # Optional MCP server registration
├── skills/
│   └── <skill-name>/
│       ├── SKILL.md         # Skill documentation and capabilities
│       ├── agents/
│       │   └── openai.yaml # OpenAI agent companion file (required)
│       ├── README.md        # Skill user documentation
│       ├── CHANGELOG.md     # Skill change history
│       ├── references/      # Optional reference documentation
│       └── scripts/         # Optional helper scripts
├── commands/
│   └── <command>.md         # Optional command documentation
├── hooks/
│   └── hooks.json           # Optional lifecycle hooks
├── monitors/
│   └── monitors.json        # Optional health check monitors
├── scripts/                 # Optional maintenance scripts
├── README.md                # Plugin documentation (required, non-empty)
└── CHANGELOG.md             # Plugin changelog (required, non-empty)
```

## Required Files

### Plugin Manifests

Every plugin that supports Claude or Codex must have the corresponding manifest:

- **`.claude-plugin/plugin.json`**: Claude plugin metadata
  - Validated against [SchemaStore](https://json.schemastore.org/claude-code-marketplace.json)
  - Defines plugin name, description, and skill directories

- **`.codex-plugin/plugin.json`**: Codex plugin metadata
  - Validated against `plugins/schemas/codex-plugin.schema.json`
  - Parallel structure to Claude manifest

- **`gemini-extension.json`**: Gemini extension manifest
  - Validated against `plugins/schemas/gemini-extension.schema.json`
  - Required when Claude or Codex manifests exist
  - May include `mcpServers` entries for MCP-backed plugins

**Requirement**: Keep `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json` aligned when adding, renaming, or removing marketplace entries. See [operations](operations.md).

### Skills and Companions

Every skill directory with `SKILL.md` must also include `agents/openai.yaml`:

- **`SKILL.md`**: Skill definition with OKF front matter
  - Defines skill capabilities, usage, and examples
  - Contains `type`, `title`, `description`, `tags`, and `timestamp` front matter

- **`agents/openai.yaml`**: OpenAI agent companion file
  - Describes the skill for OpenAI's agent runtime
  - Generated automatically by `sync-upstream-skills` when missing

**Validation**: The pre-push hook and CI check that every `SKILL.md` has a companion `openai.yaml`:
```bash
for f in $(find plugins -path '*/skills/*/SKILL.md' -type f); do
  dir=${f%/SKILL.md}
  test -f "$dir/agents/openai.yaml" || echo "missing companion: $dir"
done
```

### Documentation

Every plugin must have non-empty documentation:

- **`README.md`**: User-facing plugin documentation
  - Installation instructions
  - Usage examples
  - Configuration guidance

- **`CHANGELOG.md`**: Plugin change history
  - Notable changes per release
  - Added, changed, fixed, removed sections

**Validation**: [`plugins/scripts/check-plugin-docs`](plugins/scripts/check-plugin-docs) rejects empty README/CHANGELOG placeholders as part of `check-all`.

## Optional Components

### MCP Server Registrations

Plugins that provide MCP servers include `.mcp.json` files:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "path/to/server",
      "args": ["--arg1", "arg2"],
      "env": {
        "ENV_VAR": "value"
      }
    }
  }
}
```

These are bundled in the `main` marketplace but removed in the `marketplace-no-mcp` variant. See [marketplace model](marketplace-model.md).

### Commands

Plugins may expose CLI commands documented under `commands/*.md`:

- `vibin/commands/scaffold-claude-plugin.md`: Plugin scaffolding command
- `vibin/commands/remote-context.md`: Remote context command for Plexus
- `plexus/commands/remote-context.md`: Remote context command

Command documentation is referenced from plugin manifests and surfaced by agent runtimes.

### Hooks

Plugins may define lifecycle hooks in `hooks/hooks.json`:

```json
{
  "hooks": {
    "postInstall": "scripts/setup.sh",
    "postUpdate": "scripts/setup.sh"
  }
}
```

Common uses:
- Setup scripts that configure local services
- Validation scripts that check prerequisites
- Migration scripts that upgrade configurations

### Monitors

Plugins may define health check monitors in `monitors/monitors.json`:

```json
{
  "monitors": {
    "health": {
      "command": "scripts/health-check",
      "interval": 300
    }
  }
}
```

Monitors are used by the Labby plugin for runtime health tracking.

### Scripts

Plugins may include helper scripts under `scripts/`:

- Setup and installation scripts
- API helper scripts (e.g., `memos/scripts/memo-api.sh`)
- Validation and smoke test scripts
- Migration and upgrade scripts

Scripts should be executable when copied into plugin directories. The pre-push hook preserves executable bits.

## Representative Examples

### Vibin Plugin

The `vibin` plugin demonstrates a large multi-skill plugin:

```
plugins/vibin/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── gemini-extension.json
├── .mcp.json
├── CHANGELOG.md
├── README.md
├── commands/
│   └── scaffold-claude-plugin.md
├── hooks/
│   └── hooks.json
├── monitors/
│   └── monitors.json
└── skills/
    ├── chrome/                # Chrome DevTools integration
    ├── gh-pr/                # GitHub PR workflow skills
    ├── jetpack-compose-expert/  # Jetpack Compose expertise
    ├── paperless-ngx/        # Paperless API skills
    ├── ... (31 total skills)
    └── worktree-setup/       # Git worktree management
```

Each of the 31 skills has `SKILL.md` and `agents/openai.yaml`.

### Testing Plugin

The `testing` plugin demonstrates focused domain skills:

```
plugins/testing/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── gemini-extension.json
├── CHANGELOG.md
├── README.md
└── skills/
    ├── android-app-testing/  # Android app QA
    ├── claude-in-mobile/     # Mobile device automation
    ├── desktop-app-testing/  # Desktop app QA
    ├── mcpjam-ui-testing/    # MCP-UI/Apps validation
    ├── mcporter/             # MCP server smoke testing
    └── web-app-testing/      # Web app QA
```

### Upstream-Skills Plugin

The `upstream-skills` plugin demonstrates vendored external skills:

```
plugins/upstream-skills/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── gemini-extension.json
├── upstream-sources.json     # Manifest of vendored skills
└── skills/
    ├── autoreview/           # Vendored from openclaw
    ├── chatgpt-apps/         # Vendored from openclaw
    ├── openai-docs/          # Vendored from openclaw
    ├── ... (11 total skills)
    └── yeet/                 # Vendored from openclaw
```

Each skill is mirrored verbatim from its upstream repository, with only `agents/openai.yaml` added locally. See [vendored upstream skills](vendored-upstream-skills.md).

## Validation

The [`check-all`](plugins/scripts/check-all) script runs comprehensive validations:

```bash
plugins/scripts/check-all
```

This checks:
- Plugin manifest alignment (Claude/Codex/Gemini)
- Skill companion presence (every SKILL.md has openai.yaml)
- Plugin documentation (non-empty README/CHANGELOG)
- Marketplace manifest JSON parsing
- Upstream sources schema validation
- Generated docs consistency

## Related Documentation

- [Operations](operations.md): How to add, update, or remove plugins
- [Vendored Upstream Skills](vendored-upstream-skills.md): How external skills are synchronized
- [Marketplace Model](marketplace-model.md): Dual-branch architecture
