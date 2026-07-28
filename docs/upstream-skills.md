# Vendored Upstream Skills

The `upstream-skills` plugin (`plugins/upstream-skills/`) bundles agent skills
that are vendored **verbatim** from external repositories and kept in sync with
their sources by `plugins/scripts/sync-upstream-skills`.

This page is the maintenance reference. User-facing usage also lives in
[`plugins/upstream-skills/README.md`](../plugins/upstream-skills/README.md).

## Model

- Each skill is mirrored as a **whole folder** under
  `plugins/upstream-skills/skills/<name>/` — `SKILL.md` plus any `references/`,
  `scripts/`, and other files the upstream ships. Never vendor just `SKILL.md`.
- The only dendrite-local file per skill is `agents/openai.yaml` (the OpenAI
  companion every skill needs). It is listed in each manifest entry's
  `local_only` and is **preserved byte-for-byte** across updates. If it is
  missing after a fetch, the tool regenerates a stub from the `SKILL.md`
  frontmatter.
- Drift is detected by a content hash over the **entire** skill subtree
  (excluding `local_only`). A changed `references/*`, an edited `scripts/*`, and
  added or removed files all change the hash — not just `SKILL.md` edits.
- The tool **never commits**. It edits files and the manifest; you review
  `git diff` and commit.

## Manifest — `plugins/upstream-skills/upstream-sources.json`

Source of truth for what is vendored and from where. One entry per skill:

| field | meaning |
|-------|---------|
| `name` | skill folder name (`^[a-z0-9][a-z0-9-]*$`); derived from the URL's last path segment |
| `repo` | `owner/repo` |
| `branch` | upstream ref the skill is tracked against |
| `src_path` | path to the skill folder inside the repo (may contain dot-prefixed segments, e.g. `skills/.curated/yeet`) |
| `pinned_sha` | last vendored commit SHA (provenance + reproducible apply) |
| `content_hash` | `sha256:<hex>` fingerprint of the vendored upstream-owned files |
| `local_only` | files the tool must never overwrite or delete (default `["agents/openai.yaml"]`) |

Validated by `plugins/schemas/upstream-sources.schema.json` via
`plugins/scripts/validate-plugin-schemas` (which runs inside `check-all`). A
malformed manifest fails at validation time with a clear error.

## Commands

```bash
# Onboard a skill from a single GitHub folder URL (tree/ or blob/.../SKILL.md).
# Parses owner/repo/ref/path, vendors the folder, generates the openai.yaml
# stub, records the manifest entry. No manual manifest editing.
plugins/scripts/sync-upstream-skills add https://github.com/<owner>/<repo>/tree/<ref>/<path>

# Report drift from upstream (exit 1 if any skill drifted). CI-friendly.
plugins/scripts/sync-upstream-skills check

# Pull upstream updates into vendored skills, then review + commit.
plugins/scripts/sync-upstream-skills apply <name>      # one skill
plugins/scripts/sync-upstream-skills apply --all       # every skill

# Re-vendor an existing skill (e.g. to repoint a moved URL).
plugins/scripts/sync-upstream-skills add <url> --force
```

`add`/`apply` require an authenticated `gh` (used for the GitHub API + tarball
download).

## Workflows

**Onboard a new skill**

1. `plugins/scripts/sync-upstream-skills add <github-folder-url>`
2. (optional) hand-tune the generated `skills/<name>/agents/openai.yaml`
3. `plugins/scripts/check-all`
4. Review `git diff` and commit.

Because the plugin manifests use `"skills": "./skills/"`, a new skill folder
needs no manifest or marketplace edits — the one-time plugin scaffolding already
covers it.

**Sync existing skills**

1. `plugins/scripts/sync-upstream-skills check`
2. For anything drifted: `plugins/scripts/sync-upstream-skills apply <name>` (or
   `--all`)
3. `plugins/scripts/check-all`, review `git diff`, commit.

## Rules

- **No duplicate vendoring.** `upstream-skills` is the single sync-managed home
  for an upstream skill. Do not also add the same skill to another plugin (e.g.
  `vibin`) — two skills with the same `name` collide. (This is why `gog` was
  removed from `vibin` when it landed here.)
- **`local_only` is the contract** that keeps dendrite adaptations
  (`agents/openai.yaml`) from being clobbered on `apply`. Add to it if a skill
  grows other dendrite-local files.
- **No MCP servers** in this plugin — it ships skills only, with no `.mcp.json`
  and no Gemini `mcpServers` block.
- The tool is **stdlib-only**; its tests
  (`plugins/scripts/tests/test_sync_upstream_skills.py`) mock the network seams
  and run offline inside `check-all`.

## Currently vendored

11 skills from 5 repos: `gog` (openclaw/gogcli), `acpx` (openclaw/acpx),
`meme-maker` (openclaw/openclaw), `agent-transcript`, `autoreview`, `handoff`,
`session-viewer` (openclaw/agent-skills), and `openai-docs`, `define-goal`,
`chatgpt-apps`, `yeet` (openai/skills). See `upstream-sources.json` for the
authoritative list and pinned SHAs.
