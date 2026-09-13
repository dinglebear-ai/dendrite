---
name: review-artifacts
description: Review an existing project artifact for factual support, type-specific content completeness, source freshness, evidence integrity, and handoff readiness. Use when asked to audit or challenge a report, plan, proposal, spec, research artifact, session record, reference document, or proof harness. This reviews the artifact; it does not replace reviewing the product implementation itself.
---

# Review Artifacts

Resolve the sibling `create-artifacts` skill from this file's real installed
location. Read its `references/content-contract.md`, the relevant `types/TYPE.md`,
and the artifact itself. Inspect the subject repository's instructions when
available. For large PR dossiers, also read the PR lifecycle contract.

Run the public `contract TYPE` and scoped `validate --path ARTIFACT` commands.
Read the artifact's metadata, related sources, and its owned evidence bundles
under `<repo>/_evidence/<artifact-stem>/`. Use `evidence-verify BUNDLE` to check
sealed bytes. A digest proves retained bytes, not the truth of a claim.

Review the claims against their cited primary sources and retained observations.
Check scope, assumptions, measured versus inferred statements, decision status,
source revisions, negative results, meaningful acceptance checks, and what the
next reader needs to act. Recompute material totals from the actual records.
Do not mark a runtime claim verified by merely finding matching source text.
Do not execute harnesses, network actions, or product tests without task authority.

For plans, distinguish implementable steps from source-dependent drafts. For
research, check dates and citations. For proposals, check alternatives and the
decision requested. For PRs, check evidence applicability to the exact head and
the governed lifecycle; never treat a complete-looking UI as acceptance proof.

Return findings ordered by impact, with an exact artifact location, the claim
being challenged, supporting evidence, and a concrete correction. Separate
established defects from questions that need unavailable access. State what was
read, run, or blocked and whether the artifact is ready for its intended use.
Do not imply that a passing mechanical validator answers the semantic review.

When the user authorizes fixes, edit authoritative source (Markdown for rendered
plans), rerender when needed, and revalidate. Do not silently modify sealed
historical evidence or erase failed runs. Write a follow-up run or successor
artifact and retain lineage when the original observation must stay immutable.

For an independent pass, give a reviewer agent this skill, the artifact, and the
minimum primary evidence. Leave your preferred conclusion out of its prompt.
One bounded independent review is enough unless a concrete issue needs another.
