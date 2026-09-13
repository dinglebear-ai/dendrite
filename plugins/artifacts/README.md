# Artifacts

Create consistent engineering artifacts for every project with `$create-artifacts`.
Unraid-related work always uses the established Unraid templates. All other new
artifacts use the Aurora design system used by Labby's web application.

The plugin owns both complete template families, type contracts, fonts and brand
assets, catalog tooling, Markdown plan rendering, and the PR evidence lifecycle.
Authored outputs live at `~/artifacts/<owner-repo>/<type>/MM-DD-YY-description`.
Templates and instructions stay in Dendrite.

| Location | Ownership |
| --- | --- |
| `skills/create-artifacts/SKILL.md` | Agent routing and authoring workflow |
| `skills/create-artifacts/assets/templates/unraid` | Original Unraid templates |
| `skills/create-artifacts/assets/templates/aurora` | Matching Aurora templates |
| `skills/create-artifacts/references/types` | Evidence and content contracts |
| `skills/create-artifacts/scripts/artifacts.py` | Creation, validation, rendering, browsing, export, PR operations |
| `~/artifacts` | Created artifacts and their evidence, sources, exports, and generated indexes |

All nine categories have parity: reports, PR reports, proposals, plans, specs,
research, sessions, docs, and proof scripts. PR reports retain the original
six-stage, 29-section lifecycle and paired evidence manifests.

Use Python 3.10+ and Git. Invoke the skill with the desired project and artifact.
For direct use, resolve the installed `skills/create-artifacts` directory and run
`python3 scripts/artifacts.py --help` from there. CLI operations do not install
services, publish reports, or modify the reviewed project automatically.

Existing records are preserved by the migration mapping, including sealed
evidence and Git history. The legacy path contains compatibility links to the
single canonical copy. Source fonts are bundled for portable output.

## Development

Run `python3 -m unittest discover -s tests` from this plugin. Runtime regression
tests live under `skills/create-artifacts/references/runtime/_tests`. Read
`CLAUDE.md` before changing templates or routing. The source provenance and
license notices accompany the design assets.

## Content, Evidence, and Review

Templates include the type-specific content scaffold as well as the UI. The
shared versioned contract defines required content independently of brand;
`contract TYPE` prints it. `review-artifacts` evaluates factual support and
readiness beyond structural validation.

Use `evidence-start`, `evidence-seal`, and `evidence-verify` to keep captured and
derived files under `<repo>/_evidence/<artifact-stem>/<run-id>`. The `inventory`
command distinguishes documents from thousands of supporting files. `init-root`
links root guidance back to Dendrite. No automatic evidence deletion occurs.
