# Changelog

All notable changes to Dendrite are recorded here.

## Unreleased

### Removed

- Retired the no-MCP marketplace variant (2026-07-28). Deleted the `marketplace-no-mcp` branch, the `sync-marketplace-no-mcp.yml` and `check-no-mcp-drift.yml` workflows, `plugins/scripts/apply-no-mcp-marketplace`, `plugins/scripts/check-no-mcp-drift`, and the generated `docs/no-mcp-variant.md`. Dropped the drift step from `check-all`, the drift gate from the `.githooks/pre-push` hook, the `no-MCP ref` column from `docs/marketplace-sources.md`, and all no-MCP install/runbook guidance from the README, CONTRIBUTING, and the docs. `main` is now the only published marketplace branch.
- Removed the `arrs` plugin. Its ten per-service skills (Radarr, Sonarr, Prowlarr, Overseerr, SABnzbd, qBittorrent, Plex, Jellyfin, Tautulli, Tracearr) were merged into the standalone `rustarr` plugin (github.com/jmagar/rustarr), which now exposes the same services through its MCP server and CLI. De-registered from the Claude and Codex marketplace manifests and regenerated the inventory docs.

### Added

- Added the Vibin knowledge-layer skill suite: `wrap-session`, `log-code-session`, `log-homelab-maintenance`, `log-decisions`, `new-runbook`, `new-report`, `align-standards`, and `deploy-new-service`.
- Added a `homelab-map` context refresher that composes the existing `~/docs` inventory generators and emits a source-hashed manifest without persisting raw command output.
- Added the `gog` skill to the Vibin plugin for safe Google Workspace automation (Gmail, Calendar, Drive, Docs, Sheets, Contacts) with stable JSON output, scoped auth, and command guards; regenerated the README and plugin-matrix inventories.
- Added missing `README.md` and `CHANGELOG.md` files for all current skill directories.
- Added a curated-plugin inventory to the root `README.md`, including marketplace coverage and repo counts.
- Added Gemini CLI extension manifests for every local plugin directory.
- Added `plugins/scripts/generate-gemini-extensions` to regenerate Gemini manifests from plugin metadata, user config, and MCP snippets.
- Added the `zsnoop-mcp` plugin and skill for ZFS snapshot exploration, file recovery, and guarded restore workflows.
- Added Memos API helper coverage for current Memos v1 workflows, including authentication, memo updates, and attachment operations.
- Added dedicated Overseerr request-moderation helpers for common approve, decline, retry, and listing workflows.
- Added repeatable helper scripts for Jellyfin, Tracearr, Navidrome, AdGuard, Immich, Qdrant, TEI, Uptime Kuma, and MCPJam UI testing.
- Added schema-backed Claude/Codex/Gemini manifest validation, generated documentation checks, marketplace install smoke tests, and no-MCP drift automation.
- Added installation, marketplace operations, plugin documentation standard, configuration, and release/changelog docs.
- Added `plugins/scripts/check-plugin-docs` to reject empty plugin README/CHANGELOG placeholders.

### Changed


- Relicense Dinglebear-owned original work under AGPL-3.0-only and document separate commercial licensing; third-party material retains its original terms.
- Refactored `save-to-md` into the focused `log-code-session` logger and retained `save-to-md` as a deprecated compatibility alias. Session logging no longer commits, pushes, mutates trackers, or cleans repositories.
- Separated repository publishing from knowledge capture: `quick-push` now publishes repository changes, while `wrap-session` records final code and infrastructure state afterward.
- Reworked the Rust skill into a broader Rust-patterns skill covering the rmcp family, Lab CLI conventions, async service boundaries, UI streaming, and repository layout rules.
- Updated marketplace metadata to keep the Claude and OpenAI plugin manifests aligned.
- Moved the `creating-snippets` skill out of Dendrite and into the Labby plugin source in the Lab repository.
- Updated ByteStash documentation so snippet creation guidance lives under ByteStash-specific wording.
- Refreshed skill documentation across the plugin set with clearer verification, configuration, and operational notes.
- Restored `main` as the full/default marketplace and kept `marketplace-no-mcp` as the derived gateway-oriented variant.
- Updated generated configuration docs to include skill-body config consumers.

### Fixed

- Prevented the pre-push test suite from inheriting repository-local `GIT_*` variables that redirected temporary-repository commits into the real Dendrite worktree. The hook now clears Git-local environment, the lane-evidence test helper strips inherited Git variables, and a regression test simulates hook execution.
- Scoped the `.githooks/pre-push` no-MCP drift compare to pushes that target `main` or `marketplace-no-mcp`, so feature-branch pushes are no longer blocked by pre-existing cross-ref drift. CI still enforces the invariant via `check-no-mcp-drift.yml` and `sync-marketplace-no-mcp.yml`. `check-all` still runs on every push.
- Hardened several skill scripts and docs based on reviewer findings, including Plex token handling, mcporter output quoting, and explicit Overseerr media identifiers.
- Restored the expected skill documentation contract: every Dendrite skill now has `SKILL.md`, `agents/openai.yaml`, `README.md`, and `CHANGELOG.md`.
- Filled empty README and CHANGELOG placeholders for ByteStash, Immich, Linkding, LoggiFly, Memos, NotebookLM, and Radicale.

### Removed

- Removed the Bitwarden plugin from Dendrite and from both marketplace manifests.
- Removed duplicate or superseded Vibin skills now owned by dedicated plugins, including Agent OS, desktop app testing, and MCPJam inspection.
- Removed the duplicate Vibin `yt-dlp` skill; `ytdl-mcp` now owns that marketplace capability.
- Removed the obsolete Bitwarden-only `plugins/scripts/ensure-host-dirs` helper.
