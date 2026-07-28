# Installation

Dendrite publishes a single marketplace from `main`. Installing it registers the
full catalog, including plugin-provided MCP server registrations.

The canonical repository is `dinglebear-ai/dendrite`. The former `jmagar/dendrite`
path still resolves through GitHub's transfer redirect, but new installs should
use the canonical name.

## Claude Code

```bash
claude plugin marketplace add dinglebear-ai/dendrite
```

Claude accepts `owner/repo`, `owner/repo#ref`, `https://...`, and local paths. Do
not use the unsupported `github:owner/repo` form.

## Codex

```bash
codex plugin marketplace add dinglebear-ai/dendrite
```

Install a plugin after adding the marketplace:

```bash
codex plugin add acp@dendrite
```

## Gemini

Gemini does not install a Dendrite marketplace as a single marketplace catalog.
Install or link individual plugin directories that contain `gemini-extension.json`:

```bash
gemini extensions install plugins/acp --consent --skip-settings
gemini extensions link plugins/acp
gemini extensions validate plugins/acp
```

Gemini accepts `--ref` for whole-repository extensions, but Dendrite's Gemini
extensions live below `plugins/<name>/`, so installing from a local checkout is
the reliable path.

## Smoke Test

Run the local install smoke before publishing marketplace changes:

```bash
plugins/scripts/smoke-marketplace-install
plugins/scripts/smoke-marketplace-install --ref origin/main
```
