---
type: Workflow Concept
title: Vendored Upstream Skills
description: How external skills are vendored into Dendrite, synchronized with their sources, and validated through schema-backed manifests.
tags: [upstream, skills, sync, vendoring, validation, git]
---

# Vendored Upstream Skills

The `upstream-skills` plugin bundles agent skills vendored **verbatim** from external repositories and kept in sync with their sources by [`plugins/scripts/sync-upstream-skills`](plugins/scripts/sync-upstream-skills).

This mechanism allows Dendrite to distribute popular skills from openclaw and OpenAI while maintaining a single source of truth for provenance and updates.

## Model

### Whole-Folder Mirroring

Each skill is mirrored as a **complete folder** under `plugins/upstream-skills/skills/<name>/`:

- `SKILL.md` plus any `references/`, `scripts/`, and other files the upstream ships
- Never vendor just `SKILL.md` — mirror the entire skill subtree
- Changes to `references/*`, edited `scripts/*`, and added/removed files all count as drift

### Local-Only Files

The only dendrite-local file per skill is `agents/openai.yaml`:

- Every skill needs an OpenAI companion file
- Listed in the manifest's `local_only` field
- **Preserved byte-for-byte** across sync updates
- If missing after a fetch, the tool regenerates a stub from `SKILL.md` front matter

### Drift Detection

Drift is detected by a content hash over the **entire** skill subtree (excluding `local_only` files):

- `content_hash`: `sha256:<hex>` fingerprint of upstream-owned files
- A changed reference, edited script, or added/removed file changes the hash
- The tool never commits — you review `git diff` and commit yourself

## Manifest Structure

Source of truth is [`plugins/upstream-skills/upstream-sources.json`](plugins/upstream-skills/upstream-sources.json):

```json
{
  "skills": [
    {
      "name": "autoreview",
      "repo": "jmagar/openclaw",
      "branch": "main",
      "src_path": "skills/.curated/autoreview",
      "pinned_sha": "abc123...",
      "content_hash": "sha256:def456...",
      "local_only": ["agents/openai.yaml"]
    }
  ]
}
```

### Fields

| field | meaning |
|-------|---------|
| `name` | Skill folder name (`^[a-z0-9][a-z0-9-]*$`); derived from URL's last path segment |
| `repo` | `owner/repo` |
| `branch` | Upstream ref the skill is tracked against |
| `src_path` | Path to the skill folder inside the repo (may contain dot-prefixed segments) |
| `pinned_sha` | Last vendored commit SHA (provenance + reproducible apply) |
| `content_hash` | `sha256:<hex>` fingerprint of vendored upstream-owned files |
| `local_only` | Files the tool must never overwrite or delete (default `["agents/openai.yaml"]`) |

### Validation

Manifest is validated by [`plugins/schemas/upstream-sources.schema.json`](plugins/schemas/upstream-sources.schema.json) through [`plugins/scripts/validate-plugin-schemas`](plugins/scripts/validate-plugin-schemas), which runs inside `check-all`.

A malformed manifest fails validation with a clear error.

## Commands

### Onboard a New Skill

```bash
plugins/scripts/sync-upstream-skills add <github-folder-url>
```

Parses owner/repo/ref/path from a GitHub folder URL (tree/ or blob/.../SKILL.md), vendors the folder, generates the `openai.yaml` stub, and records the manifest entry. No manual manifest editing required.

**Example:**
```bash
plugins/scripts/sync-upstream-skills add https://github.com/jmagar/openclaw/tree/main/skills/.curated/autoreview
```

### Check Drift

```bash
plugins/scripts/sync-upstream-skills check
```

Reports drift from upstream (exit 1 if any skill drifted). CI-friendly.

### Apply Updates

```bash
plugins/scripts/sync-upstream-skills apply <name>       # One skill
plugins/scripts/sync-upstream-skills apply --all        # Every skill
```

Pulls upstream updates into vendored skills. Review `git diff` and commit yourself.

### Re-vendor a Skill

```bash
plugins/scripts/sync-upstream-skills add <url> --force
```

Useful when a skill moved or you need to repoint its URL.

## Workflows

### Onboard a New Skill

1. Run `sync-upstream-skills add <github-folder-url>`
2. Optionally hand-tune the generated `skills/<name>/agents/openai.yaml`
3. Run `plugins/scripts/check-all`
4. Review `git diff` and commit

The plugin manifests use `"skills": "./skills/"`, so a new skill folder needs no manifest or marketplace edits — the one-time plugin scaffolding already covers it.

### Sync Existing Skills

1. Run `plugins/scripts/sync-upstream-skills check` to report drift
2. Run `plugins/scripts/sync-upstream-skills apply --all` to pull updates
3. Review `git diff` for unexpected changes
4. Commit and run `plugins/scripts/check-all`

### Repoint a Moved Skill

If an upstream skill moved or changed structure:

1. Run `sync-upstream-skills add <new-url> --force`
2. Review the diff for the re-vendored subtree
3. Update any plugin-specific overrides in `local_only`
4. Commit and validate

## Current Vendored Skills

From [`plugins/upstream-skills/upstream-sources.json`](plugins/upstream-skills/upstream-sources.json):

**From openclaw:**
- `acpx`: ACP/X implementation patterns
- `agent-transcript`: Claude session transcript analysis
- `autoreview`: Automatic code review generation
- `chatgpt-apps`: ChatGPT Apps SDK patterns
- `define-goal`: Goal definition and planning
- `gog`: Google Workspace automation
- `handoff`: Agent handoff workflows
- `meme-maker`: Meme generation from templates
- `session-viewer`: Claude session viewer and HTML export
- `yeet`: Bulk file deletion with guards

**From OpenAI:**
- `openai-docs`: OpenAI documentation patterns and references

## Requirements

The `add` and `apply` commands require an authenticated `gh` CLI for GitHub API access and tarball downloads.

```bash
gh auth status  # Verify authentication
```

## Related Documentation

- [Plugin Structure](plugin-structure.md): How skills are organized within plugins
- [Operations](operations.md): Common maintenance workflows
- [Automation](automation.md): CI/CD workflows and validation scripts
