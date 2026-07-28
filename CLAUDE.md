# Dendrite Agent Instructions

`CLAUDE.md` is the source of truth for agent memory in this repo. `AGENTS.md`
and `GEMINI.md` must be symlinks to this file.

## Purpose

Dendrite owns the portable Claude Code, Codex, and Gemini plugin marketplace.
It carries plugin sources, skills, MCP config snippets, commands, hooks,
scripts, Gemini extension manifests, and OpenAI agent companion files.

This is not a Rust repo — there is no `Cargo.toml` and no build step. The
deliverables are JSON manifests, Markdown skills, and the Python/Bash scripts
under `plugins/scripts/` that generate and validate them.

Remote: `git@github.com:dinglebear-ai/dendrite.git`. Default branch: `main`.
`main` is the only published marketplace branch.

The Lab control-plane plugin is the exception: `plugins/labby` stays in
`dinglebear-ai/labby` and is referenced from both marketplace manifests as a
`git-subdir` source at `https://github.com/dinglebear-ai/labby.git:plugins/labby`.
That repo was formerly `jmagar/lab`; the old URL still works only through
GitHub's transfer redirect, so keep the manifests on the canonical name.

## Repository Rules

- Do not add `plugins/labby` to this repo.
- Keep `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`
  aligned when adding, renaming, or removing marketplace entries.
- Every skill directory with `SKILL.md` must also include
  `agents/openai.yaml`.
- Plugin manifests live under `.claude-plugin/plugin.json` and
  `.codex-plugin/plugin.json` when both agent runtimes are supported.
- Keep secrets out of the repo. Plugin config hooks may write local config files,
  but committed examples must not contain real credentials.
- Preserve executable bits on scripts and hooks when copying plugin directories.
- Plugin README and CHANGELOG files must be useful, not empty placeholders.
  `plugins/scripts/check-plugin-docs` enforces this as part of `check-all`.

## Generated Files

Several tracked files are generated and must not be hand-edited. Change the
inputs, then rerun the generator:

| Generated file | Generator |
|---|---|
| `README.md` inventory and curated-plugins blocks (between the `GENERATED README INVENTORY` / `GENERATED CURATED PLUGINS` markers) | `plugins/scripts/generate-readme-inventory` |
| `docs/plugin-matrix.md`, `docs/configuration-matrix.md`, `docs/marketplace-sources.md`, `docs/schema-provenance.md` | `plugins/scripts/generate-docs` |
| `plugins/*/gemini-extension.json` | `plugins/scripts/generate-gemini-extensions` |

`plugins/scripts/check-all` runs each generator in `--check` mode, so stale
generated output fails the build.

## Vendored Upstream Skills

The `plugins/upstream-skills` plugin holds skills vendored verbatim from external
repos and kept in sync by `plugins/scripts/sync-upstream-skills`. Full reference:
`docs/upstream-skills.md`.

- Each `plugins/upstream-skills/skills/<name>/` mirrors a whole upstream skill
  folder (SKILL.md plus any references/scripts). The only dendrite-local file per
  skill is `agents/openai.yaml`; the sync tool preserves it across updates.
- Source of truth for provenance is `plugins/upstream-skills/upstream-sources.json`
  (repo, branch, src_path, pinned commit SHA, content hash, local_only), validated
  by `plugins/schemas/upstream-sources.schema.json` through
  `plugins/scripts/validate-plugin-schemas`.
- Onboard a skill with `sync-upstream-skills add <github-folder-url>` — it parses
  repo/ref/path from the URL, vendors the folder, generates the `openai.yaml`
  stub, and records the manifest entry. No manual manifest editing.
- `sync-upstream-skills check` reports drift (whole-subtree content hash, so
  references/scripts/added/removed files all count). `sync-upstream-skills apply
  [names…|--all]` pulls updates. The tool never commits — review `git diff` and
  commit yourself, then run `plugins/scripts/check-all`.
- Do not also vendor the same upstream skill into another plugin (e.g. `vibin`).
  `upstream-skills` is the single sync-managed home; duplicates collide on skill
  name. The tool's unit tests live at
  `plugins/scripts/tests/test_sync_upstream_skills.py` and run inside `check-all`.

## Common Checks

```bash
# No local labby plugin copy.
test ! -e plugins/labby

# The one command to run before pushing. Runs manifest parsing, schema
# validation, script unit tests, marketplace alignment, plugin docs, and every
# generator in --check mode.
plugins/scripts/check-all

# Smoke Claude, Codex, and Gemini marketplace/extension installs in temp homes.
plugins/scripts/smoke-marketplace-install

# Plugin README and CHANGELOG files must exist and contain useful content.
plugins/scripts/check-plugin-docs

# Claude and Codex marketplace entries must stay aligned by plugin name and
# normalized source target. Local plugins with Claude or Codex manifests must
# also have a sibling gemini-extension.json.
plugins/scripts/check-marketplace-sync

# Validate plugin and marketplace manifests. Claude uses published SchemaStore
# schemas. Codex and Gemini use local docs-derived schemas under plugins/schemas;
# Gemini extensions are also checked with the official `gemini extensions
# validate` command.
plugins/scripts/validate-plugin-schemas

# Print the upstream docs/source files used to maintain local Codex and Gemini
# schemas. Use this before changing plugins/schemas/*.
plugins/scripts/audit-upstream-schema-sources

# Vendor a new upstream skill from a single GitHub folder URL, then check/apply
# drift for the vendored skills. See docs/upstream-skills.md.
plugins/scripts/sync-upstream-skills add <github-folder-url>
plugins/scripts/sync-upstream-skills check
plugins/scripts/sync-upstream-skills apply --all

# Regenerate README inventory plus docs/plugin-matrix.md,
# docs/configuration-matrix.md, docs/marketplace-sources.md, and
# docs/schema-provenance.md after changing manifests, config, schemas, or
# skills.
plugins/scripts/generate-readme-inventory
plugins/scripts/generate-docs

# Enable the tracked pre-push hook in a clone.
git config core.hooksPath .githooks

# Every skill has an OpenAI companion file.
for f in $(find plugins -path '*/skills/*/SKILL.md' -type f | sort); do
  dir=${f%/SKILL.md}
  test -f "$dir/agents/openai.yaml" || echo "missing companion: $dir"
done

# Marketplace manifests parse.
jq empty .claude-plugin/marketplace.json
jq empty .agents/plugins/marketplace.json
```
