# docs/

Standing reference: how things are, and how they must be done. Docs are durable — they describe rules, contracts, and evidence packages that stay true until deliberately revised.

## Belongs here

Working contracts, operating rules, evidence packages, glossaries, onboarding references, fill-in-the-blank templates meant for *other people's work* (as opposed to `_template.html`, which templates artifacts in this directory).

## Does not belong here

- Point-in-time findings → `reports/`
- Required behavior of a component being built → `specs/`
- What happened on a given day → `sessions/`

The test: would this still be correct in six months if nobody touched it? If it decays, it is a report or a session log.

## Required structure

Same scraped elements as every artifact. Use the `.verified` aside for **applicability**: scope, rule count, how many are mandatory, and when it was last reviewed. A doc with no review date is a doc nobody trusts.

## The doc bar

Every rule carries:

1. **Do / Do not** in the `.trace` — the required pattern and the forbidden shortcut, with what the shortcut breaks.
2. **Why**, in the `.fix` block — the incident, invariant, or constraint the rule comes from. **A rule without a stated reason gets ignored, then deleted by someone who assumed it was arbitrary.**
3. **A non-compliance scan** in `.evidence` — the command that finds violations and what clean output looks like. Rules that cannot be checked drift.
4. **A `.limit`** — known exceptions and who may grant new ones. Recommended,
   not enforced: a rule is not a claim about observed behaviour, so the proof
   boundary the linter demands in `reports/` does not apply here.

Be specific enough that two readers cannot disagree about whether the rule was followed. Ambiguity in a contract is where the argument happens later.

## Revising

Edit in place and update the review date; do not append "UPDATE:" sections. Docs are read top-down by people looking for the current rule, not the rule's history. If the history matters, it belongs in a session log this doc links to.

## Not governed here

Close by naming adjacent concerns this document does not rule on, and which document owns them. Overlapping contracts that both half-claim a topic are worse than neither claiming it.

## Metadata

Fill in the `<meta name="artifact.*">` block under the `<title>`. `status`,
`date`, and `topic` are required; the linter fails without them. Use `related`
to name the artifacts this one answers or feeds — that lineage is how someone
finds the rest of the chain.

