# Contributing

Use this guide when changing Dendrite marketplace entries, plugin packaging, or
generated docs.

Keep `README.md` user-facing. Installation, marketplace selection, and catalog
orientation belong there; release maintenance, validation procedures, and
packaging details belong in this file or the docs under `docs/`.

## Marketplace Model

- `main` is the only published marketplace branch. It may include
  plugin-provided MCP server registrations when those registrations are useful
  for a normal install.
- External plugin sources should be referenced from the marketplace manifests
  instead of copied into this repository.

## Plugin Layout

- Keep local portable marketplace plugins in `plugins/<name>/`.
- Every skill at `plugins/*/skills/*/SKILL.md` must have
  `agents/openai.yaml` next to it.
- Local plugins with `.claude-plugin/plugin.json` or
  `.codex-plugin/plugin.json` must also have `gemini-extension.json`.
- Keep `.claude-plugin/marketplace.json` and
  `.agents/plugins/marketplace.json` aligned when adding, renaming, or removing
  marketplace entries.
- Plugin README and CHANGELOG files should contain useful content, not empty
  placeholders.

## Add Or Update A Local Plugin

1. Put source under `plugins/<name>/`.
2. Add or update `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`.
3. Add or update `gemini-extension.json`.
4. Ensure every `skills/*/SKILL.md` has `agents/openai.yaml`.
5. Add useful `README.md` and `CHANGELOG.md` files.
6. Add matching entries to `.claude-plugin/marketplace.json` and
   `.agents/plugins/marketplace.json`.
7. Regenerate generated files and run checks.

```bash
plugins/scripts/generate-gemini-extensions
plugins/scripts/generate-readme-inventory
plugins/scripts/generate-docs
plugins/scripts/check-all
plugins/scripts/smoke-marketplace-install
```

## Add Or Update A Curated Remote Plugin

1. Prefer `git-subdir` when the plugin lives below a repository subdirectory.
2. Pin external third-party plugins by `sha` when practical.
3. Keep Claude and Codex entries normalized to the same repo/path/ref/sha.
4. Regenerate docs.

```bash
plugins/scripts/generate-docs
```

## Remove A Plugin

1. Remove both marketplace entries.
2. Remove the local plugin directory if Dendrite owns it.
3. Regenerate docs and run the full checks.

## Required Checks

```bash
plugins/scripts/check-all
plugins/scripts/smoke-marketplace-install
```
