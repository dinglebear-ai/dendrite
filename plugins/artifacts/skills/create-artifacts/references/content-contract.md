# Content Authority

Templates prescribe content as well as presentation. Both brands implement the
same artifact-type contract. Changing the brand must never change the evidence
standard or omit required content.

The authority is layered:

1. The user's task and the subject repository's instructions define scope and facts.
2. `contracts/types.json` defines each type's question, required content, structural
   checks, and semantic review questions. Run `artifacts.py contract TYPE` to read it.
3. `types/TYPE.md` explains how to meet those requirements. The PR lifecycle
   registry remains authoritative for its 29 sections.
4. `assets/templates/{unraid,aurora}/TYPE` is the authoring scaffold: layout,
   component styles, content slots, and examples. An example is never evidence.

Start with the template and replace every instruction with real content. A
source file, captured observation, or cited primary source owns factual claims;
no template supplies facts. Preserve stable finding/requirement IDs across edits.
Keep proof boundaries visible and label proposed, inferred, measured, not-run,
blocked, and unknown states distinctly.

New outputs carry `artifact.contract-version: 1`. Structural validation checks
record completeness in addition to the existing metadata and markup checks.
It cannot prove truth, sound reasoning, adequate source coverage, or execution
readiness. Use `review-artifacts` for that judgment. A green structural check is
not an approval or a verification claim.

For a deliberately empty result, explain it with `artifact.empty-reason` and a
visible account of scope and method; do not invent findings to fill cards. Keep
checks proportional to the work. Low-impact documentation edits do not require
an artificial failing-test/implementation/commit sequence.

Historical artifacts keep their original contract until deliberately revised.
A contract or template update never silently rewrites their evidence. Record
review date, consulted source revisions, and a successor link when superseding
an artifact. Update durable docs in place; preserve historical reports as dated
observations. Do not treat age alone as grounds for deleting evidence.
