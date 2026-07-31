---
title: Configuration
created: 2026-07-30
updated: 2026-07-30
---

# Configuration

Dendrite plugins use runtime-specific plugin settings where available. Setup
hooks may mirror those settings into private local env files for shell helpers
and skills.

The generated inventory lives in `docs/configuration-matrix.md`.

## Local Config Files

Many homelab service plugins write:

```bash
${XDG_CONFIG_HOME:-~/.config}/lab-<service>/config.env
```

These files are local-only, mode `600`, and should never be committed. Legacy
`~/.lab/.env` fallback remains for migration but should not be the first choice
for new setup.

## Runtime Mapping

- Claude Code stores userConfig values through plugin settings.
- Codex reads plugin options as `CODEX_PLUGIN_OPTION_*` where supported by the
  plugin hook/script.
- Gemini extension settings map to env vars declared in `gemini-extension.json`.

## Secrets

Sensitive values include API keys, bearer tokens, passwords, and auth headers.
Docs and examples must use placeholders only. Do not paste real credentials into
plugin manifests, generated docs, screenshots, or session notes.

## Updating Config Metadata

When adding a config key:

1. Add it to Claude and Codex plugin manifests.
2. Add the matching Gemini setting.
3. Update setup hooks or helper scripts that consume it.
4. Run `plugins/scripts/generate-docs`.
5. Verify `docs/configuration-matrix.md` lists the key and its consumers.
