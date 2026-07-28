---
type: Repository Overview
title: Dendrite Plugin Marketplace
description: Portable plugin catalog for Claude Code, Codex, and Gemini that packages agent skills, MCP server registrations, commands, hooks, and companion metadata in one place.
tags: [marketplace, plugins, skills, claude-code, codex, gemini, mcp]
---

# Dendrite Plugin Marketplace

[Dendrite](https://github.com/jmagar/dendrite) is a portable plugin catalog for Claude Code, Codex, and Gemini. It packages agent skills, MCP server registrations, commands, hooks, config helpers, Gemini extension manifests, and OpenAI companion metadata in a single repository.

This OpenWiki knowledge base explains how Dendrite works, how to maintain it, and where to find key files and workflows.

## What Dendrite Provides

Dendrite delivers practical agent capabilities across multiple runtimes from one marketplace source:

- **Workflow automation**: Full development loops with `vibin` (worktrees, commits, PRs, CI debugging, session logs)
- **App testing**: Web, Android, and desktop app testing skills through the `testing` plugin
- **Homelab and services**: Focused skills for Paperless, Qdrant, Neo4j, Linkding, AdGuard, Dozzle, Scrutiny, SWAG, Navidrome, and related tools
- **MCP development**: Build and maintain MCP servers and plugins with `acp`
- **Review workflows**: Curated plugins for stronger review and coding practices
- **Knowledge and search**: Search, RAG, and research helpers

See [README.md](README.md) for the full plugin inventory and installation instructions.

## Key Concepts

### Plugins and Skills

A **plugin** is a package that contains one or more **skills** plus optional metadata. Each skill is a self-contained agent capability documented in `SKILL.md` with an accompanying `agents/openai.yaml` for OpenAI agents.

Plugins live under `/plugins/<name>/` and contain:
- Plugin manifests (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `gemini-extension.json`)
- Skills (`skills/*/SKILL.md`)
- MCP server registrations (`.mcp.json`)
- Command documentation (`commands/*.md`)
- Hooks (`hooks/hooks.json`)
- Helper scripts (`scripts/*`)

See [plugin structure](plugin-structure.md) for the complete layout.

### Marketplace Variants

Dendrite maintains two marketplace branches:

- **`main`**: The full/default marketplace with MCP server registrations included
- **`marketplace-no-mcp`**: A generated variant without bundled MCP registrations for gateway-oriented environments

The no-MCP variant is automatically synchronized from `main` via CI/CD. See [marketplace model](marketplace-model.md) for details.

### Vendored Upstream Skills

The `upstream-skills` plugin bundles skills vendored verbatim from external repositories and kept in sync via `sync-upstream-skills`. These include popular skills from openclaw and OpenAI that are mirrored locally rather than referenced as external marketplace entries.

See [vendored upstream skills](vendored-upstream-skills.md) for the sync workflow and maintenance procedures.

## Where to Start

### For Users

If you want to install and use Dendrite plugins:
1. Read [installation instructions](README.md#marketplace-installation)
2. Browse the [plugin inventory](README.md#inventory) to find capabilities you need
3. Install the marketplace: `claude plugin marketplace add jmagar/dendrite`

### For Contributors

If you want to add or update plugins:
1. Read [plugin structure](plugin-structure.md) to understand the layout
2. Review [marketplace operations](operations.md) for add/update/remove workflows
3. Follow the [common checks](CLAUDE.md#common-checks) before submitting

### For Maintainers

If you maintain the marketplace:
1. Understand the [marketplace model](marketplace-model.md) and no-MCP variant
2. Review [automation](automation.md) for CI/CD workflows and scripts
3. Use [operations](operations.md) as a reference for maintenance tasks
4. Keep [CLAUDE.md](CLAUDE.md) current as the source of truth for agent memory

## Plugin Categories

**Workflow Automation**
- `vibin`: Development loops, Git workflows, GitHub PRs, Windows utilities, Jetpack Compose expertise

**Testing**
- `testing`: Web, Android, and desktop app testing; MCP tooling validation

**Homelab and Services**
- `agent-os`: Windows 11 sandbox VM control
- `adguard`, `bytestash`, `dozzle`, `immich`, `linkding`, `memos`, `navidrome`, `neo4j`, `paperless-ngx` (via `vibin`), `qdrant`, `radicale`, `scrutiny`, `swag`, `tei`, `uptime-kuma`, `zsnoop-mcp`

**MCP Development**
- `acp`: Rust implementation patterns for ACP and rmcp-derived MCP servers

**Knowledge and Search**
- `notebooklm`: Research and generation workflows
- `upstream-skills`: Vendored skills including agent-transcript, autoreview, chatgpt-apps, openai-docs, and more

See [source map](source-map.md) for complete file locations.

## Documentation Overview

This OpenWiki covers:

- **[Marketplace Model](marketplace-model.md)**: Dual-branch architecture and no-MCP variant
- **[Plugin Structure](plugin-structure.md)**: Standard plugin layout and required files
- **[Vendored Upstream Skills](vendored-upstream-skills.md)**: How external skills are synchronized
- **[Operations](operations.md)**: Common maintenance workflows
- **[Automation](automation.md)**: CI/CD workflows and validation scripts
- **[Source Map](source-map.md)**: Quick navigation to key files

The OpenWiki is regenerated on a schedule by the [OpenWiki Update workflow](.github/workflows/openwiki-update.yml). Do not hand-edit generated pages unless explicitly asked; prefer updating source code and letting OpenWiki regenerate.
