# specs/

What a thing must do, stated so precisely that someone who did not write it can verify it. A spec defines required behavior and its acceptance checks — it is the contract an implementation is measured against.

## Belongs here

Requirement sets, interface and API contracts, replacement/parity requirements, acceptance criteria, behavioral contracts for a component being built or rebuilt.

## Does not belong here

- What the current system does today → `reports/`
- Why we chose this shape → `proposals/`
- The order of building it → `plans/`
- Standing rules about how work is done → `docs/`

## Required structure

Same scraped elements as every artifact. Use the `.verified` aside for **counts by priority**: must-have, should-have, explicitly-out, open questions. The first `.stats` figure should be the must-have count — that is the number that tells a reader how big this really is.

## The spec bar

Every requirement carries:

1. **Given / When / Then** in the `.trace` — starting state, action, required observable result. If you cannot phrase it this way, it is a wish, not a requirement.
2. **An acceptance check** in the `.fix` block — how a reviewer verifies it *without asking the author*. This is the difference between a spec and a memo.
3. **The exact interface** in `.evidence` — signature, schema, payload, route. Real shapes, not prose descriptions of shapes.
4. **A `.limit`** — the deliberate non-goal. Recommended, not enforced: a
   requirement is not an evidentiary claim, so the linter does not demand a
   proof boundary here the way it does in `reports/`. What this requirement does not demand, so implementers do not gold-plate it.

Number requirements (`M1`, `M2`, `S1`…) and never renumber them. Other artifacts, tickets, and commits cite these IDs.

## Testability is the gate

A requirement nobody can check is not a requirement. Before adding one, write its acceptance check first. If the check is "reviewer judgment", either sharpen it or move it to `docs/` as guidance.

## Explicitly out of scope

Close with behavior a reasonable reader would assume is included and is not. Most spec disputes are about the unwritten assumption, not the written requirement.

## Metadata

Fill in the `<meta name="artifact.*">` block under the `<title>`. `status`,
`date`, and `topic` are required; the linter fails without them. Use `related`
to name the artifacts this one answers or feeds — that lineage is how someone
finds the rest of the chain.
