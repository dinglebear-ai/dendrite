# Artifact Directory Routing

Use the `create-artifacts` skill from the Artifacts plugin in
`~/workspace/dendrite/plugins/artifacts`. Resolve the installed skill's real path
and read its SKILL.md plus the relevant type contract before authoring.

The artifact's subject repository determines the family: every Unraid-related
artifact uses Unraid; every other new artifact uses Aurora. Both families obey
the same type-specific content requirements. Preserve historical designs and
evidence. Use `review-artifacts` for content and evidence review.

Write human-facing outputs under `<owner-repo>/<type>/MM-DD-YY-description.*`.
Allocate bulk evidence/model runs with `evidence-start` under the repository's
`_evidence` directory. Keep raw observations separate from derived/model output.
Seal completed runs, verify hashes, and start a new run for retries. Do not
rewrite sealed historical files or remove failed runs to make results look clean.

Edit Markdown for generated plans. Validate the scoped artifact and verify its
evidence before handing it off; green markup checks do not prove factual claims.
Keep templates, scripts, contracts, and maintainable instructions in Dendrite.
Root README/AGENTS/CLAUDE/GEMINI entries are symlinks to that maintained guidance.
Do not place dependencies, model weights, caches, or reusable tooling here.

Never push to the Unraid GitHub organization without the user's explicit
permission. Creation or review does not authorize publishing, deployment,
messages, services, or executing the product's verification workloads.
