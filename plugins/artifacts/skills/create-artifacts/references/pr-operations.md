# PR Operations

Read the [PR report contract](types/pr-reports.md). Use the public wrapper to
create the HTML and evidence manifest as one package:

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" pr-new --help
```

Supply the exact `--repository`, `--branch`, `--base 'branch @ FULL_SHA'`,
`--head-sha`, `--merge-base`, `--worktree`, and `--topic`. Supply `--pr` when the
PR exists. The helper verifies the local Git identity by default, selects the
project family, and writes
`~/artifacts/owner-repo/pr-reports/MM-DD-YY-branch-description.html` with a sibling
`.evidence.jsonl`. It refuses an existing report or manifest. Full SHA values
must come from actual repository or authenticated GitHub evidence.

`--allow-unverified` records a visible provenance caveat when local identity
cannot be established. `--github-authoritative` is valid only after reading an
actual fresh API snapshot; it does not collect that snapshot for the agent.
Neither option converts unavailable evidence into verification. Pass
`--unraid-related` for any Unraid subject not identified by owner, repository
name, configured identity, or an inspected Unraid upstream. In GitHub-authoritative
mode, determine that relationship from the API/context because local Git is not
consulted.

The retained operations are available with:

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" pr --help
```

The compiler, evidence classifications, revision ledger, decision history,
freshness checks, finalizer, and seal live together under `references/runtime`.
Its lifecycle registry is
`references/runtime/pr-reports/schema/sections.json`.
All 29 sections are retained for both template families. Fill section-specific
unknown/not-run/not-applicable explanations instead of deleting sections.

For direct advanced helpers named by the type contract, resolve them under
`$SKILL_DIR/references/runtime/scripts/`; use absolute report and evidence paths.
Do not run legacy repository-specific harnesses against a different project.
Commands that inspect GitHub, capture shell evidence, or execute repository
checks require the corresponding access and task authorization.

Unraid publication restrictions remain in force. Creating a private dossier
does not authorize PR publication, remote comments, merging, or pushing. Keep
private provenance out of a public PR payload.
