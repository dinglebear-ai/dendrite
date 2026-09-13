# sessions/

A durable record of one working session: what was asked, what was actually done, and where it was left. Written for whoever picks this up cold — including you, next week.

## Belongs here

Working logs, handoff notes, incident timelines, debugging narratives, "here is the state I left this in" writeups.

## Does not belong here

- Conclusions that outlive the session → promote to `reports/` or `docs/`
- Work still to be sequenced → `plans/`
- Anything true only because of *when* it was written, that nobody will read again → do not write it at all

A session log is the one artifact type scoped to a moment. Everything else here is meant to stay true. If a finding in your session log matters next month, it belongs in another folder — the log should link to it, not be its only home.

## Required structure

Same scraped elements as every artifact. Use the `.verified` aside for **session shape**: duration, files changed, commands run, and how it ended (complete / handed off / blocked).

## The session bar

Each entry carries:

1. **Intent → Action → Result** in the `.trace`. Past tense.
2. **Exact commands and their real output** in `.evidence`. Not cleaned up. Not the command you meant to run.
3. **State now** in the `.fix` block — where this left the repo, the branch, the service.
4. **A `.limit`** — what you left unverified, and why.

## Record the wrong turns

A log that only shows the path that worked teaches nothing and quietly implies the work was easier than it was. Include the approaches that failed and what ruled them out. That is most of the value here.

## Name the artifacts in play

A session almost always produces, consumes, or should be reconciled against
other artifacts here. Carry an **Artifacts in play** section listing each one
with a working relative link and a sentence on the actual relationship —
produced, consumed, corroborates, supersedes. Declare the same paths in
`artifact.related` so the index can draw the lineage both ways.

List what you did **not** read as well, when it shares the topic. An unstated
absence reads as coverage, and the next reader has no way to tell a deliberate
scope boundary from an oversight.

## Open threads are the payload

Close with everything the next session needs to pick up: where it stands, what blocks it, and the obvious next move — written so it can be acted on **without** this session's context. If a reader has to reconstruct your reasoning to continue, the log failed at its one job.

## Metadata

Fill in the `<meta name="artifact.*">` block under the `<title>`. `status`,
`date`, and `topic` are required; the linter fails without them. Use `related`
to name the artifacts this one answers or feeds — that lineage is how someone
finds the rest of the chain.
