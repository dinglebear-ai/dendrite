# proposals/

An argument for a specific change, with the alternatives that were considered and rejected. A proposal exists to get a decision made — it ends in an approve/reject, not in a task list.

## Belongs here

Design blueprints, port/migration recommendations, architecture change arguments, build-vs-buy cases, remediation strategies that require sign-off.

## Does not belong here

- Establishing what is broken → `reports/`
- Executing a decision already made → `plans/`
- The contract the decision produced, once settled → `docs/`

Sequence matters: a report finds the problem, a proposal argues the fix, a plan sequences it, a doc records the rule it became. Do not collapse two stages into one artifact — a proposal that also sequences the work makes the decision hard to see and hard to reject.

## Required structure

Same scraped elements as every artifact (`<title>`, `.eyebrow`, hero `<p>`, `.verified` rows, first `.stats` pair). Use the `.verified` aside for the **decision set**: how many recommendations are for now, deferred, rejected, and what verification backs them.

## The proposal bar

Each recommendation carries:

1. **The change as an imperative** — "Lease every dispatch boundary", not "Dispatch boundary leasing".
2. **The options you rejected, and why.** A recommendation with no discarded alternative is a preference, not a proposal. Put them in the `.trace` — losing options first, recommended option last.
3. **Cost and blast radius** — modules touched, migration needed, rollback path, rough effort. In `.evidence`.
4. **The invariant preserved** — in the `.fix` block. What must still be true after the change.
5. **A `.limit`** — what the proposal does not address, and **what evidence would change the recommendation.** Name the thing that would make you withdraw it.

## Say what you are not proposing

The closing "Not proposed" section lists tempting adjacent changes you deliberately left out. This is scope armour: it stops the proposal from quietly growing between review and execution.

## Respect existing authority

When Core already owns a concern maturely, say so and leave it alone. A proposal that rewrites a working subsystem to match a preferred shape will be rejected on those grounds — name the authorities you are not touching, explicitly.

## Metadata

Fill in the `<meta name="artifact.*">` block under the `<title>`. `status`,
`date`, and `topic` are required; the linter fails without them. Use `related`
to name the artifacts this one answers or feeds — that lineage is how someone
finds the rest of the chain.
