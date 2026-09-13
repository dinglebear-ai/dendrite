# Artifact Plugin Instructions

This plugin is the sole source of truth for artifact authoring. Read
`skills/create-artifacts/SKILL.md` for the workflow and follow its project/type
routing. Root-level `AGENTS.md` and `GEMINI.md` point to this file.

For every Unraid-related artifact use `assets/templates/unraid` under the skill,
including forks, staging repos, QA, E2E, and plugins. For every other newly created
artifact use `assets/templates/aurora`. Preserve existing artifact designs and
recorded evidence. Never infer the subject from the plugin checkout's own owner.

Keep the output directory free of copied instructions, templates, package source,
test suites, and build environments. Root guidance may link to the maintained
`references/output-*.md` files. Bulk evidence belongs in `<repo>/_evidence/`,
owned by artifact and run. Content authority is documented in the shared
content contract; both template families must implement it. Store generated artifacts and accompanying
evidence at `~/artifacts/<owner-repo>/<type>/MM-DD-YY-description`.

Preserve all nine type contracts and the complete PR-report lifecycle when
changing either family. Unraid template bytes are pinned in design-provenance;
do not change those templates as a side effect of Aurora work. Aurora values,
typefaces, icon vocabulary, identity, and component treatments come from the
inspected Aurora sources, with provenance and notices maintained alongside them.

The runtime is retained from the original artifact system. Public operations go
through `scripts/artifacts.py`; keep its independent output root and package
resource resolution. Do not reintroduce a dependency on a Core checkout for
ordinary artifact creation or require a populated catalog to create the first
artifact. Existing proof harnesses are historical outputs, not automatic checks
to run against an unrelated project.

Validate project routing, template parity, path containment and collisions,
plan rendering, PR creation/evidence, mixed-brand browsing, and fresh exports.
Inspect rendered output for each changed family. Migration must be planned
first, preserve a backup, verify file hashes, preserve user changes and Git
history, and leave a dated receipt. Do not alter historical evidence to make
new paths appear in a previously recorded observation.

Skill invocation does not authorize network publication. Never push to the
Unraid organization without explicit user permission.
