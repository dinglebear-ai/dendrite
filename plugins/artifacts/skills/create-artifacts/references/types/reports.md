# reports/

What is true about a system right now, established by evidence. A report audits something that already exists and answers "what is actually happening here?" — it does not argue for a change.

## Belongs here

Audits, findings ledgers, parity inventories, gap analyses, post-incident reconstructions. Anything whose payload is **facts about the current state**, each one independently checkable.

## Does not belong here

- Arguing for a specific change → `proposals/`
- Sequencing already-approved work → `plans/`
- Defining what a thing must do → `specs/`
- Answering an open question with uncertainty → `research/`

A report may — and usually should — carry a `.fix` block per finding stating the required invariant. That does not make it a proposal. The test: strip every recommendation out. If what remains is still the point of the document, it is a report.

## Required structure

The index scrapes these; a report missing them renders as a card with holes.

- `<title>Unraid Core — Report Name</title>`
- `<div class="eyebrow">Area / what was audited</div>` — text after `/` becomes the card tag
- first `<p>` after the eyebrow — the card description
- `<aside class="verified">` rows — the card's fact column; use them for **suite results and worktree state**, not for findings counts
- `<section class="stats">` — its first `.num`/`.label` becomes this report's column in the index stat strip

## The evidence bar

This is the whole reason the folder exists. Every finding carries:

1. **A causal trace** — `.trace` steps from precondition to observable consequence. Three steps is usually right. If you cannot write the middle step, you have not found the bug yet.
2. **Verbatim observed output** — in `.evidence`. Never paraphrase output. Never reformat numbers.
3. **Clickable source locations** — `file:///Users/jmagar/workspace/core/...#L<line>`, one per claim, labelled with what is at that line.
4. **A stated boundary** — the `.limit` block. What this proof does *not* establish. **A finding without a `.limit` does not ship.**

Tag honestly, using the tag classes as they are defined:

- `.runtime` — reproduced on a running system
- `.path` — code-path proof only; the behavior was read, not executed
- `.high` / `.medium` — severity

Never pick a tag for visual balance. A code-path finding tagged `runtime` is a lie the design system helps you tell.

## Code snippets vs. evidence

`.evidence` blocks hold **observed output** and stay verbatim and uncoloured —
colouring output implies a syntax it does not have. When a finding genuinely
needs a *source snippet*, use a `.code` block instead and generate its markup:

```bash
python3 "$SKILL_DIR/references/runtime/scripts/highlight-snippet.py" ~/workspace/core/lib/unraid/plugin/loader.ex elixir --lines 240-252
```

Never hand-write the token spans.

## Excluded claims stay visible

Every report ends with an "Excluded from the finding count" section listing claims that failed the proof pass and why. Deleting them silently inflates the headline number. The excluded section is what makes the count trustworthy.

## Numbers propagate

`index.html` reads your `.stats` and `.verified` values. Re-run the harness and update them when the report changes, or a stale number spreads to the index.

## Metadata

Fill in the `<meta name="artifact.*">` block under the `<title>`. `status`,
`date`, and `topic` are required; the linter fails without them. Use `related`
to name the artifacts this one answers or feeds — that lineage is how someone
finds the rest of the chain.

