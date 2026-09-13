---
name: create-artifacts
description: Create and maintain repository-scoped HTML engineering reports, PR dossiers, proposals, Markdown implementation plans, specs, research, session records, reference docs, and proof harnesses. Use when asked to create or update project artifacts, render plans, browse the artifact catalog, or export an artifact package with Unraid or Aurora templates.
---

# Create Artifacts

Use this plugin as the source of truth for artifact templates, evidence contracts,
renderers, and validation. Save authored outputs under `~/artifacts`; do not copy
the skill, templates, instructions, tests, or reusable tooling into that directory.
An explicit output root from the user takes precedence.

## Choose the Project and Template

Resolve the artifact's actual subject repository as `owner/repository`, using the
task, its checkout instructions, and Git remotes. The artifact's subject decides
the template; the current working directory does not. Use `local/project-name`
for a project that has no remote owner, with the user's established project name.

- **Every Unraid-related artifact uses Unraid templates**, including Unraid
  forks, plugins, QA/E2E work, staging repositories, and cross-project work whose
  subject is Unraid. Do not restyle those artifacts with Aurora.
- **Every other newly created artifact uses Aurora templates.**
- The `route` command recognizes Unraid/Limetech owners, repository prefixes,
  known staging repositories in [projects.json](references/projects.json), and
  Unraid upstream remotes when `--worktree` is supplied. Pass
  `--unraid-related` when task context establishes a relationship the repository
  identity alone cannot show. There is no override to force Unraid work into Aurora.
- Preserve the design and recorded evidence of existing artifacts when editing
  or migrating them. A template update does not authorize rewriting old findings.

Resolve `SKILL_DIR` to the absolute directory containing this `SKILL.md` in the
installed plugin or Dendrite checkout. Keep that value for subsequent commands.

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" route \
  --repository dinglebear-ai/labby --worktree "$PROJECT_CHECKOUT"
```

Templates live under `assets/templates/{unraid,aurora}/<artifact_type>/`.
Read [Design and Template Parity](references/design.md) before visual work and
the one relevant type contract below before authoring its content.

| Artifact Type | Purpose and Contract | Template |
| --- | --- | --- |
| `reports` | [Checkable findings](references/types/reports.md) | `_template.html` |
| `pr-reports` | [Complete PR lifecycle and evidence](references/types/pr-reports.md) | `_template.html` plus paired manifest |
| `proposals` | [Recommendation and rejected alternatives](references/types/proposals.md) | `_template.html` |
| `plans` | [Approved work and executable steps](references/types/plans.md) | `_template.md`, rendered to HTML |
| `specs` | [Requirements and acceptance checks](references/types/specs.md) | `_template.html` |
| `research` | [Open questions, confidence, and falsifiers](references/types/research.md) | `_template.html` |
| `sessions` | [Intent, actions, results, and open work](references/types/sessions.md) | `_template.html` |
| `docs` | [Durable rules and reference](references/types/docs.md) | `_template.html` |
| `scripts` | [Runnable proof harnesses](references/types/scripts.md) | `_template.sh` |

## Create and Complete an Artifact

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" new \
  --repository unraid/core --type reports --date 2026-09-13 \
  --slug storage-lifecycle-review --worktree "$PROJECT_CHECKOUT"
```

The helper creates a scaffold exclusively at
`~/artifacts/unraid-core/reports/09-13-26-storage-lifecycle-review.html`.
It refuses existing destinations and ambiguous repository directory identities.
For an alternate output root, place `--root /absolute/output` **before** the
subcommand. The date is the artifact's evidence/work date, not a fabricated
verification date. Use a stable descriptive slug.

Fill every instructional placeholder with actual content. Keep required sections
and state `Not run`, `Unknown`, or `Not applicable`, with a reason, where needed.
Do not turn template sample numbers or example command output into findings.
Report evidence verbatim, link consulted sources, distinguish inference, and
state what each proof does not establish. Preserve `.evidence` blocks when
changing layout. Add required metadata: `id`, `status`, `date`, `topic`,
`repository`, and `brand`; the helper fills these. `artifact.related` contains
paths relative to the artifact root, including `owner-repo/`.

For a plan, edit its Markdown source and then render it:

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" render-plan /absolute/path/to/plan.md
```

For a PR report, use [PR Operations](references/pr-operations.md). Its verified
repository/branch identity, paired evidence manifest, lifecycle compiler,
revision ledger, and seal are required. Do not use `new` or hand-copy the HTML
for an ordinary PR report.

## Validate and Deliver

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" validate --path /absolute/path/to/artifact.html
python3 "$SKILL_DIR/scripts/artifacts.py" index
```

Fix issues in the artifact or its source. Check rendered HTML at desktop and
phone widths when creating a visual artifact or changing its layout. Verify
theme behavior, loaded fonts, navigation, expandable content, tables, and code
overflow. Template scaffolds intentionally fail content validation until filled.
Historical failures elsewhere do not establish a failure in the new artifact;
keep the scoped validation result and the full-catalog status distinct.

Use `serve --open` for local browsing. Use `export --out /absolute/new-folder`
for a portable snapshot; the destination must not exist. See
[Operations](references/operations.md) for browsing, source views, exports,
and [Migration](references/migration.md) for preserved legacy records.

Report the artifact path and meaningful verification limits. Commit scoped
changes when working in a Git-backed artifact checkout; skill invocation alone
does not authorize pushes, publication, deployments, service changes, or messages.
Never push to the `unraid` organization without the user's explicit authorization.
