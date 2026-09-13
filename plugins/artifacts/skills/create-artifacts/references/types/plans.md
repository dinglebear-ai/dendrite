# plans/

The ordered sequence of work that delivers an already-approved outcome, written so a fresh engineer with no context can execute it task by task. A plan assumes the decision is made; its job is decomposition, exact code, and verification at every step.

## Two files, one source of truth

A plan exists twice, for two different readers:

| File | Reader | Written by |
| --- | --- | --- |
| `08-27-26-feature.md` | **Agents.** Executed task by task; `- [ ]` steps get ticked as work lands. | You, following this plan contract |
| `08-27-26-feature.html` | **Humans.** The shareable artifact — progress, tasks, files, and constraints in the design system. | the public `render-plan` command, from the Markdown |

The **Markdown is the source of truth**. The HTML is generated and carries
`<meta name="artifact.generated">` naming its source; the index shows one card
per plan (the HTML) and links back to the `.md`. Never hand-edit the HTML — the
next render overwrites it, and the tooling errors if the `.md` is newer.

Re-render after ticking steps off, and the artifact's progress updates with it:

```bash
python3 "$SKILL_DIR/scripts/artifacts.py" render-plan ~/artifacts/owner-repo/plans/08-27-26-feature.md
```

The Markdown carries the metadata as YAML front matter, and the renderer copies
it into the HTML:

```yaml
---
artifact.status: draft
artifact.date: 2026-08-27
artifact.repository: owner/repo
artifact.brand: aurora
artifact.topic: feature
artifact.related: owner-repo/specs/08-27-26-what-this-implements.html
---
```

## Belongs here

Implementation plans, migration runbooks, phased rollouts, refactor orderings.

## Does not belong here

- The argument for doing it at all → `proposals/`
- The requirements it must satisfy → `specs/`
- A log of what actually happened when you ran it → `sessions/`

If nobody has approved the direction yet, you are writing a proposal. Writing
the plan first is how unapproved work acquires momentum.

## Who you are writing for

Assume the engineer is skilled but knows **nothing** about our toolset or problem
domain, and has questionable taste in test design. Document which files to touch,
the actual code, the exact command to run, and the output that means success. If
a step makes them guess, the plan failed.

## Required shape

The linter enforces all of this:

- **Header** — the agentic-worker banner describing the execution workflow, then
  `**Goal:**` (one sentence), `**Architecture:**` (2-3 sentences),
  `**Tech Stack:**`.
- **`## Global Constraints`** — project-wide requirements, one line each, values
  copied verbatim from the spec. Every task inherits them.
- **`## File Structure`** — every file to create or modify, and what each one is
  responsible for, **before** any task is defined. This is where decomposition
  gets locked in. One responsibility per file; files that change together live
  together; follow the target repo's existing patterns rather than restructuring.
- **`### Task N:` sections**, each with:
  - **`**Files:**`** — exact paths, with line ranges for modifications.
  - **`**Interfaces:**`** — what this task Consumes and Produces, as exact
    signatures. A task's implementer sees only their own task; this block is the
    only way they learn the names and types their neighbours chose.
  - **checkbox steps** — one concrete action each, with observable verification. Use
    failing-test → implementation → passing-test steps when they prove meaningful
    behavior. A documentation-only task can have one actionable edit/check step
    with its command and expected result. Do not invent tests or require commits
    solely to fill a template. Implementation steps show the actual code.

## What the renderer colours

the public `render-plan` command derives colour from structure you already write. Keep
these conventions and the artifact reads at a glance; break them and it degrades
to plain text rather than breaking.

| In the Markdown | In the artifact |
| --- | --- |
| `Create:` / `Modify:` / `Test:` / `Delete:` / `Read:` starting a **Files:** line | A coloured verb badge — green for new, amber for edits, red for deletions |
| `Consumes:` / `Produces:` starting an **Interfaces:** line | A small label, with `backticked` signatures syntax-highlighted |
| Step titles using the TDD wording | A coloured dot per step kind: red for the failing test, orange for implementation, green for the passing verification |
| `Run:` and `Expected:` in step prose | Bold labels, with `PASS` green and `FAIL` red |
| A language tag on every fence | Syntax highlighting plus a corner label |

The step-kind colours are the reason to keep the standard wording: a task whose
dots skip green has no passing verification, and you can see that without
reading it.

## Task right-sizing

A task is the smallest independently verifiable deliverable that is worth a fresh
reviewer's gate. Fold setup, configuration, scaffolding, and docs into the task
whose deliverable needs them. Split only where a reviewer could meaningfully
reject one task while approving its neighbour. Each task ends with an
independently testable deliverable.

## No placeholders — these are plan failures

The linter rejects them by name: "TBD", "TODO", "implement later", "add
appropriate error handling", "handle edge cases", "write tests for the above"
with no test code, "similar to Task N" (repeat the code — tasks get read out of
order), and any reference to a function or type no task defines.

## Before handing off

Run the self-review yourself; it is a checklist, not a subagent dispatch.

1. **Spec coverage** — point at the task that implements each spec requirement.
   Add tasks for gaps.
2. **Placeholder scan** — the list above.
3. **Type consistency** — `clear_layers/1` in Task 3 and `clear_full_layers/1`
   in Task 7 is a bug. Check every Interfaces block against its consumers.

Then delete the self-review section and offer the execution choice:
subagent-driven (fresh subagent per task, review between tasks) or inline.

## Scope check

If the spec spans multiple independent subsystems, split it into one plan per
subsystem. Each plan must produce working, testable software on its own.


Resolve `SKILL_DIR` from the loaded skill. Optional planning/execution skills may
assist when available; this contract is self-contained. A preserved Unraid
template may name historical sub-skills. Adapt that banner to available tooling
in the authored plan. When checkout evidence is missing, keep the plan draft,
label proposed paths and interfaces as unverified, and record the blocking
verification step instead of inventing exact implementation facts.
