---
type: Navigation Reference
title: Source Map
description: Quick navigation to key files, directories, and configurations in the Dendrite repository.
tags: [navigation, source-map, files, directories]
---

# Source Map

This page provides quick navigation to key files and directories in the Dendrite repository.

## Core Documentation

| File | Purpose |
|------|---------|
| [README.md](README.md) | User-facing installation, marketplace selection, catalog orientation |
| [CLAUDE.md](CLAUDE.md) | Agent instructions, repository rules, long-lived branches |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Marketplace model, plugin layout, contribution workflows |
| [CHANGELOG.md](CHANGELOG.md) | Feature history and notable changes |

## Operational Documentation

| File | Purpose |
|------|---------|
| [docs/marketplace-operations.md](docs/marketplace-operations.md) | Add/update/remove marketplace entries |
| [docs/upstream-skills.md](docs/upstream-skills.md) | Vendored upstream skills maintenance |
| [docs/marketplace-sources.md](docs/marketplace-sources.md) | External plugin sources |
| [docs/configuration-matrix.md](docs/configuration-matrix.md) | Configuration coverage |
| [docs/plugin-matrix.md](docs/plugin-matrix.md) | Plugin and skill inventory |
| [docs/no-mcp-variant.md](docs/no-mcp-variant.md) | No-MCP marketplace variant details |
| [docs/installation.md](docs/installation.md) | Installation examples |
| [docs/plugin-documentation-standard.md](docs/plugin-documentation-standard.md) | Documentation requirements |
| [docs/schema-provenance.md](docs/schema-provenance.md) | Schema sources |
| [docs/release-and-changelog.md](docs/release-and-changelog.md) | Release process |

## Marketplace Manifests

| File | Purpose |
|------|---------|
| [.claude-plugin/marketplace.json](.claude-plugin/marketplace.json) | Claude marketplace manifest (77 entries) |
| [.agents/plugins/marketplace.json](.agents/plugins/marketplace.json) | Codex/OpenAI marketplace manifest (77 entries) |

## Marketplace Plugins by Category

### Workflow Automation

| Plugin | Description | Skills Count |
|--------|-------------|--------------|
| [plugins/vibin](plugins/vibin) | Development loops, Git workflows, GitHub PRs, Windows utilities, Jetpack Compose expertise | 31 |

### Testing

| Plugin | Description | Skills Count |
|--------|-------------|--------------|
| [plugins/testing](plugins/testing) | Web, Android, and desktop app testing; MCP tooling validation | 6 |

### Homelab and Services

| Plugin | Description | Skills Count |
|--------|-------------|--------------|
| [plugins/agent-os](plugins/agent-os) | Windows 11 sandbox VM control | 1 |
| [plugins/adguard](plugins/adguard) | AdGuard Home DNS-level ad blocking | 1 |
| [plugins/bytestash](plugins/bytestash) | ByteStash snippet manager | 1 |
| [plugins/dozzle](plugins/dozzle) | Real-time Docker container log viewer | 1 |
| [plugins/immich](plugins/immich) | Self-hosted photo and video management | 1 |
| [plugins/linkding](plugins/linkding) | Linkding bookmark manager | 1 |
| [plugins/loggifly](plugins/loggifly) | Docker container log alerting | 1 |
| [plugins/memos](plugins/memos) | Memos note hub | 1 |
| [plugins/navidrome](plugins/navidrome) | Navidrome music server | 1 |
| [plugins/neo4j](plugins/neo4j) | Neo4j graph database | 1 |
| [plugins/qdrant](plugins/qdrant) | Qdrant vector database | 1 |
| [plugins/radicale](plugins/radicale) | Radicale CalDAV/CardDAV server | 1 |
| [plugins/scrutiny](plugins/scrutiny) | SMART disk health monitoring | 1 |
| [plugins/swag](plugins/swag) | SWAG reverse proxy configuration | 1 |
| [plugins/tei](plugins/tei) | Text Embeddings Inference server | 1 |
| [plugins/uptime-kuma](plugins/uptime-kuma) | Uptime Kuma monitoring | 1 |
| [plugins/zsnoop-mcp](plugins/zsnoop-mcp) | ZFS snapshot exploration | 1 |

### Development

| Plugin | Description | Skills Count |
|--------|-------------|--------------|
| [plugins/acp](plugins/acp) | Rust implementation patterns for ACP and rmcp-derived MCP servers | 1 |
| [plugins/plexus](plugins/plexus) | Remote-device memory and live operating context | 2 |

### Knowledge and Search

| Plugin | Description | Skills Count |
|--------|-------------|--------------|
| [plugins/notebooklm](plugins/notebooklm) | NotebookLM research and generation workflows | 1 |
| [plugins/upstream-skills](plugins/upstream-skills) | Vendored skills from openclaw and OpenAI | 11 |

## Maintenance Scripts

| Script | Purpose |
|--------|---------|
| [plugins/scripts/check-all](plugins/scripts/check-all) | Run comprehensive validation suite |
| [plugins/scripts/check-plugin-docs](plugins/scripts/check-plugin-docs) | Validate plugin documentation |
| [plugins/scripts/check-marketplace-sync](plugins/scripts/check-marketplace-sync) | Ensure marketplace alignment |
| [plugins/scripts/check-no-mcp-drift](plugins/scripts/check-no-mcp-drift) | Compare no-MCP variant with transform |
| [plugins/scripts/validate-plugin-schemas](plugins/scripts/validate-plugin-schemas) | Validate manifests against schemas |
| [plugins/scripts/audit-upstream-schema-sources](plugins/scripts/audit-upstream-schema-sources) | Print schema provenance |
| [plugins/scripts/generate-gemini-extensions](plugins/scripts/generate-gemini-extensions) | Regenerate Gemini extension manifests |
| [plugins/scripts/generate-readme-inventory](plugins/scripts/generate-readme-inventory) | Regenerate README inventory |
| [plugins/scripts/generate-docs](plugins/scripts/generate-docs) | Regenerate generated documentation |
| [plugins/scripts/apply-no-mcp-marketplace](plugins/scripts/apply-no-mcp-marketplace) | Apply no-MCP transform |
| [plugins/scripts/sync-upstream-skills](plugins/scripts/sync-upstream-skills) | Sync vendored upstream skills |
| [plugins/scripts/smoke-marketplace-install](plugins/scripts/smoke-marketplace-install) | Smoke-test marketplace installs |
| [plugins/scripts/health-check](plugins/scripts/health-check) | Run basic health checks |

## CI/CD Configuration

| File | Purpose |
|------|---------|
| [.github/workflows/openwiki-update.yml](.github/workflows/openwiki-update.yml) | Scheduled OpenWiki documentation updates |
| [.github/workflows/sync-marketplace-no-mcp.yml](.github/workflows/sync-marketplace-no-mcp.yml) | Sync no-MCP variant from main |
| [.github/workflows/check-no-mcp-drift.yml](.github/workflows/check-no-mcp-drift.yml) | Check no-MCP drift on schedule |
| [.github/workflows/validate-marketplaces.yml](.github/workflows/validate-marketplaces.yml) | Validate manifests on push/PR |
| [.githooks/pre-push](.githooks/pre-push) | Pre-push validation hook |

## Schemas

| File | Purpose |
|------|---------|
| [plugins/schemas/codex-plugin.schema.json](plugins/schemas/codex-plugin.schema.json) | Codex plugin manifest schema |
| [plugins/schemas/gemini-extension.schema.json](plugins/schemas/gemini-extension.schema.json) | Gemini extension manifest schema |
| [plugins/schemas/upstream-sources.schema.json](plugins/schemas/upstream-sources.schema.json) | Upstream sources manifest schema |
| [plugins/schemas/codex-marketplace.schema.json](plugins/schemas/codex-marketplace.schema.json) | Codex marketplace manifest schema |
| [plugins/schemas/codex-marketplace.schema.json](plugins/schemas/codex-marketplace.schema.json) | Codex marketplace manifest schema |

## Plugin Reference Structures

### Vibin Plugin (31 Skills)

```
plugins/vibin/
├── skills/
│   ├── check-skill-clis/       # Skill CLI validation
│   ├── chrome/                 # Chrome DevTools integration
│   ├── claude-android-ninja/   # Android development expertise
│   ├── clipboard/              # Clipboard utilities
│   ├── compose-skill/          # Compose Multiplatform expertise
│   ├── create-swag-config/     # SWAG proxy configuration
│   ├── create-unraid-plugin/   # Unraid plugin scaffolding
│   ├── fastmcp-client-cli/     # FastMCP client tools
│   ├── gh-fix-ci/              # GitHub CI workflow fixes
│   ├── gh-pr/                  # GitHub PR workflows
│   ├── hand-off/               # Agent handoff patterns
│   ├── homelab-map/            # Homelab documentation generation
│   ├── jetpack-compose-expert/ # Jetpack Compose expertise
│   ├── merge-status/           # Merge status checks
│   ├── monolith-check/         # Monolith enforcement
│   ├── nircmd/                 # Windows NirCmd utilities
│   ├── paperless-ngx/          # Paperless API skills
│   ├── quick-push/             # Quick Git push utilities
│   ├── rclone/                 # Rclone integration
│   ├── refresh-docs/           # Documentation refresh workflows
│   ├── repo-status/            # Repository status reporting
│   ├── resume-work-lanes/     # Work lane evidence collection
│   ├── review-pr/              # PR review workflows
│   ├── save-to-md/             # Markdown save utilities
│   ├── screenshots/            # Screenshot capture
│   ├── submit-unraid-community-app/ # Unraid app submissions
│   ├── sysinternals/           # Windows Sysinternals tools
│   ├── using-rmcp/             # rmcp usage patterns
│   ├── validate-skill/        # Skill validation
│   ├── work-it/                # Task execution workflows
│   └── worktree-setup/         # Git worktree management
```

### Testing Plugin (6 Skills)

```
plugins/testing/
└── skills/
    ├── android-app-testing/    # Android app QA
    ├── claude-in-mobile/       # Mobile device automation
    ├── desktop-app-testing/    # Desktop app QA
    ├── mcpjam-ui-testing/      # MCP-UI/Apps validation
    ├── mcporter/               # MCP server smoke testing
    └── web-app-testing/        # Web app QA
```

### Upstream-Skills Plugin (11 Skills)

```
plugins/upstream-skills/
└── skills/
    ├── acpx/                   # ACP/X patterns (from openclaw)
    ├── agent-transcript/       # Session analysis (from openclaw)
    ├── autoreview/             # Code review (from openclaw)
    ├── chatgpt-apps/           # ChatGPT Apps (from openclaw)
    ├── define-goal/            # Goal planning (from openclaw)
    ├── gog/                    # Google Workspace (from openclaw)
    ├── handoff/                # Handoff patterns (from openclaw)
    ├── meme-maker/             # Meme generation (from openclaw)
    ├── openai-docs/            # OpenAI docs (from OpenAI)
    ├── session-viewer/         # Session export (from openclaw)
    └── yeet/                   # File deletion (from openclaw)
```

## Related Documentation

- [Quickstart](quickstart.md): Entry point and overview
- [Marketplace Model](marketplace-model.md): Dual-branch architecture
- [Plugin Structure](plugin-structure.md): Standard plugin layout
- [Operations](operations.md): Maintenance workflows
- [Automation](automation.md): CI/CD and scripts
