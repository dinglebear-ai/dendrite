# Artifact Operations

The installed skill is self-contained. Python 3.10+ and Git support ordinary
creation, validation, rendering, and browsing. PR evidence operations may use
additional explicitly selected repository tools; inspect their `--help` first.
No package installation or service activation occurs on skill invocation.

Resolve `SKILL_DIR` from the loaded skill. The public CLI is
`python3 "$SKILL_DIR/scripts/artifacts.py"`.

| Command | Behavior |
| --- | --- |
| `route --repository owner/repo [--worktree PATH] [--unraid-related]` | Resolve identity and family without writing |
| `new --repository owner/repo --type TYPE --slug NAME [--date YYYY-MM-DD]` | Create an exclusive scaffold |
| `render-plan PATH.md [--repository owner/repo]` | Render the authoritative Markdown with the selected family |
| `validate [--path PATH] [--json]` | Check evidence, metadata, markup, links, and project routing |
| `index` | Generate the portable root `index.html` catalog |
| `serve [--port 8787] [--open]` | Browse on localhost, with search, related artifacts, source views, and changes |
| `export --out NEW_DIRECTORY` | Write a fresh portable snapshot; never delete or replace an existing export |
| `pr-new ...` | Verified PR report creation and paired evidence manifest |
| `pr ...` | Retained PR compiler and evidence lifecycle operations |

The optional global `--root PATH` goes before the subcommand. It defaults to
`~/artifacts` and can also be set using `ARTIFACTS_ROOT`. A user-specified root
always wins. Framework resources are resolved from the installed plugin.

The catalog groups artifacts by repository and type. Topic-based related links
stay inside a repository; explicit lineage can cross repositories. Markdown
plans are represented by their rendered card and link to their original source.
New outputs carry their canonical owner/repository to catch directory slug
collisions. Repository slugs normalize punctuation, so never infer identity
solely by reversing a hyphenated folder name.

Raw and source views are scoped to published catalog entries. The local server
does not expose the plugin checkout or arbitrary files. Private PR records and
their historical local paths remain private material: a local export is not a
public release or a substitute for the separately audited PR public summary.

An exported snapshot embeds fonts and maps consulted local source citations
using the recorded repository map. Unmapped local citations become labeled
text; do not claim that an unavailable source was verified. Add newly consulted
repository citation mappings to the package's configured map when needed.

Framework changes belong in Dendrite. Authored artifacts, paired Markdown,
evidence, exported snapshots, and migration receipts belong in the output
repository. Do not place agent instructions or templates in `~/artifacts`.

Read [Content Authority](content-contract.md) for shared type requirements and
[Evidence Storage](evidence.md) for artifact-owned runs. `contract TYPE` exposes
the content contract, `inventory` separates human-facing items from supporting
files, and `init-root` installs canonical guidance symlinks. `review-artifacts`
adds semantic review of facts and readiness to the mechanical validator.
