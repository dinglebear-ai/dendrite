# scripts/

Runnable code: the harnesses that prove the claims made elsewhere in this directory, with captured results retained as evidence. Reusable catalog, renderer, validator, and service code belongs exclusively in the Dendrite plugin. Everything here is read-only with respect to the repositories it inspects.

## Belongs here

Proof harnesses (`prove-*.sh`), empirical measurement scripts (`*.exs`), and other project-specific proof harnesses.

Nothing that mutates a target repository. These scripts are run by people checking a claim they did not make; inspect their commands and target before running; a read-only intent does not authorize execution automatically.

## The harness bar

1. **`set -euo pipefail`** at the top. A harness that continues past a failed check reports false confidence.
2. **One assertion per claim, in the report's order**, labelled with what a PASS proves. A reader should be able to hold the report and the output side by side.
3. **Print the target commit and worktree state first.** A PASS against unknown source proves nothing.
4. **Exit non-zero on any failure**, loudly. Silent degradation is the failure mode these scripts exist to catch elsewhere.
5. **Close by printing the boundary** — what a full PASS does not prove. Mirror the `.limit` blocks in the report it backs.

## Grep is weaker than execution

`require_text` proves a code path *exists*, not that it *executes*. When you assert on source text rather than running the real module, say so in the harness output and in the report's `.limit`. Prefer calling production modules (as `empirical-plugin-evidence.exs` does) whenever it is safe.

## Create and Validate

Resolve `SKILL_DIR` from the loaded skill. Create a dated scaffold with:

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" new --repository owner/repo --type scripts --slug claim-proof
```

Keep the generated `# artifact.*` metadata comments. Fill every instruction,
resolve the real checkout path, and connect the harness to its report with
root-relative `artifact.related`. The template family is recorded even though
plain-text harnesses have no visual branding.

Run `bash -n PATH.sh` and the public `validate --path PATH.sh` command. The
validator checks structure, metadata, placeholders, and shell syntax; it does
not execute evidence commands. Execute the completed harness only within the
user-authorized verification scope and retain its actual output and exit code.

For catalog, rendering, local browsing, and portable export, use the commands
in [Artifact Operations](../operations.md). For paired PR evidence, read
[PR Operations](../pr-operations.md). Advanced reusable helpers live under
`$SKILL_DIR/references/runtime/scripts/`; never copy them to the output root.
