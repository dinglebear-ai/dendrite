---
name: work-it
description: Use when the user asks to "work it", execute a plan in a worktree, create a progress-tracked PR, or run a mandatory review-and-fix loop over all touched files until lint, tests, CI, and reviews are green.
---

# Work It

## Overview

Use this skill to run a plan to completion in a tracked worktree PR. Treat the
active worktree as owned for the duration: pre-existing failures, stale tests,
lint issues, review findings, CI failures, and PR comments in that worktree must
be fixed before claiming completion.

## Required Dependencies

Hard-stop if any required dependency or equivalent capability is unavailable:

- `vibin:worktree-setup` — invoke this first for any new worktree and read its
  `SKILL.md` plus its referenced files/resources before creating or syncing the
  worktree.
- `superpowers:executing-plans` — the implementation agent must execute the
  requested plan through this workflow.
- `vibin:merge-status` — final read-only merge-readiness gate before completion.
- Agent dispatch — implementation must happen in a dedicated implementation
  agent inside the worktree, not in the coordinator session.
- `lavra:lavra-review` — the one and only review run, at the end of the
  workflow.
- GitHub/forge CLI access for PR creation, CI status, and comment resolution.
- `vibin:quick-push` for final publish and session logging.

## Explicit Workflow Restriction

- **NEVER use `superpowers:subagent-driven-development` for any task.** This
  skill's implementation workflow is `superpowers:executing-plans` with one
  dedicated implementation agent, followed by one final `lavra:lavra-review`
  and verification. Do not substitute, combine, or layer
  `superpowers:subagent-driven-development` onto this workflow.

The only review is one final `lavra:lavra-review`. Do not invoke
`vibin:review-pr`, the PR Review Toolkit, additional review agents, or any
other review workflow. If `lavra:lavra-review` is unavailable, stop and report
the workflow as blocked instead of substituting another review.

## Worktree Policy

- If currently on the local `main`/`master`/default checkout, always create a
  new `.worktrees/<slug>` checkout through `vibin:worktree-setup` before editing.
- If already inside a worktree and there are no signs of other agent or human
  activity in that worktree, do not create another worktree. Run the
  `worktree-setup` doctor/sync path as needed, then continue there.
- If already inside a worktree but ownership is unclear — dirty files you did
  not create, unexpected recent commits, an active branch/PR owned by someone
  else, or other evidence of concurrent activity — stop and ask, or create a
  separate worktree from the intended base if the user asked for autonomous
  execution.

Signs of other activity include dirty files that predate the task, unpushed
commits not made by this run, background processes, active PR updates by another
actor, or worktree metadata showing another session is operating there.

## Non-Negotiables

- Invoke `vibin:worktree-setup` before creating, entering, or reusing the
  implementation worktree. Follow its `.worktrees/` placement, warm-sync, and
  safety rules.
- Read the requested plan file before implementation. Copy it into the worktree
  before dispatching the implementation agent, preserving the relative path when
  possible or using `docs/plans/imported/` when the source is outside the repo.
- Dispatch a dedicated implementation agent inside the worktree. Its prompt must
  require `superpowers:executing-plans`, the copied plan path, the base branch,
  worktree path, branch name, PR URL if already created, repo validation hints,
  and the requirement that all implementation and repair work happen inside the
  worktree.
- Create a draft PR as soon as the worktree branch exists and has been pushed,
  before implementation begins when possible. This makes progress trackable via
  commits and CI while the work proceeds. If the forge requires a non-empty diff,
  create the PR immediately after the first focused commit.
- Commit early and commit often. Prefer small, reviewable commits after coherent
  plan slices, verification repairs, and review-fix batches.
- Keep all implementation, final review fixes, verification, commits, PR
  updates, and PR comment resolution inside the worktree.
- Fix every issue surfaced by verification, the single final
  `lavra:lavra-review`, CI, and PR comments. Pre-existing issues in the
  worktree are in scope.
- Do not resolve PR comments until the matching code or documentation change is
  committed, pushed, and verified, or the comment is proven obsolete with
  evidence.
- Do not finish while background jobs, review agents, or CI checks are still
  running.

## Workflow

1. **Prepare or reuse the worktree**
   - Inspect live state: `git status --short --branch`, `git branch
     --show-current`, `git remote -v`, and `git worktree list --porcelain`.
   - Apply the worktree policy above.
   - Invoke `vibin:worktree-setup`. For a new branch, create under
     `.worktrees/<slug>`; for an existing worktree, run the sync/doctor flow.
   - Enter the worktree for all remaining commands and record base branch,
     worktree path, branch name, and HEAD.

2. **Load and copy the plan**
   - Read the plan path supplied by the user.
   - Copy the plan into the worktree before dispatch. Preserve repo-relative
     paths when the plan is inside the source checkout; otherwise copy to
     `docs/plans/imported/<original-name>.md`.
   - Convert the plan into a coordinator checklist for the implementation agent,
    PR tracking, the final review, and final gates.

3. **Create the tracking PR**
   - Push the branch with upstream tracking.
   - Create a draft PR with `gh pr create` as soon as the branch can support it.
   - Include the plan summary, copied plan path, intended verification, and note
     that implementation is in progress.
   - If a PR cannot be created until the first diff exists, make the first
     focused implementation commit and create the PR immediately afterward.

4. **Dispatch implementation agent to green**
   - Dispatch one implementation agent whose working directory is the worktree
     root.
   - Require the agent to invoke `superpowers:executing-plans` and execute the
     copied plan file from inside the worktree.
   - Require scoped commits as plan slices are completed.
   - Require the agent to iterate until the whole worktree is green: lint,
     formatting, tests, build, typecheck, generated artifacts, config examples,
     docs, and repo-specific gates.
   - Require a concise handoff with changed files, plan items completed,
     verification commands and results, remaining risks, and whether the
     worktree is clean or dirty.
   - Require that handoff to be preserved for the final `vibin:wrap-session`
     closeout. The coordinator owns the final routing and must carry the
     implementation handoff into the code-session log.
   - When the agent returns, inspect `git status --short`, review changed files
     enough to understand the implementation, and rerun the reported
     verification before proceeding.

5. **Resolve PR comments and CI**
   - Fetch open PR comments/reviews with the repo's accepted tooling or `gh`
     CLI/API fallback.
   - Address every actionable comment in the worktree.
   - Push fixes, verify again, and resolve comments only after fixes are present
     remotely.
   - Repeat fetch, fix, verify, push, and resolve until there are zero
     unresolved actionable comments.
   - Check CI status and wait/retry as needed until all CI is green.

6. **Run the single final review**
   - After implementation, PR comment resolution, and CI are green, run
     exactly one `lavra:lavra-review` inside the worktree.
   - Address every finding, regardless of severity.
   - Re-run relevant verification after each fix batch and push follow-up
     commits to the PR. Do not run another review afterward.

7. **Log the final session state**
   - Invoke `vibin:quick-push` from the worktree so repository changes are
     committed and pushed before final session evidence is captured.
   - Invoke `vibin:wrap-session` after the push and final verification state is
     known. This workflow is code-only unless live infrastructure was also
     changed, in which case the router must create both artifacts.
   - Ensure the code-session log captures branch, final HEAD, worktree path, PR
     URL, verification commands/results, the single final review, comments
     resolved, remaining risks, and open questions.
   - Do not make `quick-push` stage or publish files from the personal knowledge
     base.

8. **Final gate**
   - Invoke `vibin:merge-status` from the worktree, using its collector script
     and `--run-checks` when the local checks are safe to execute.
   - If merge-status reports `not_ready`, `blocked`, or `unverified`, loop back
     into fixes or stop with the blocking evidence. Do not publish as complete.
   - Linting must be clean.
   - All tests must pass.
   - All CI must be green.
   - Any and all pre-existing issues in the worktree must be resolved.
   - Review/comment queues must be empty or explicitly non-actionable with
     evidence.
   - `git status --short` must be clean except for intentionally untracked
     ignored artifacts.

9. **Publish final status**
    - Do not create new commits after the final gate. If any final report or
      note would change tracked files, write it before rerunning the final gate.
    - Push only if the final gate left already-validated commits unpushed, then
      re-check CI for the pushed HEAD before claiming completion.

## Agent Dispatch Guidance

Use agents when the runtime supports them and the user asked for this full
workflow. Keep ownership explicit:

- Implementation agent: execute the copied plan with
  `superpowers:executing-plans` inside the worktree and return only after the
  plan is implemented and verification is green.
- Do not invoke `superpowers:subagent-driven-development` under any
  circumstances; it is explicitly disallowed by this skill.
- Review agent: run exactly one final `lavra:lavra-review`; do not dispatch any
  other review agent or invoke any other review workflow.

If no agent-dispatch mechanism exists, stop and report the implementation phase
as blocked. Do not silently self-implement the plan in the coordinator session.

## Completion Standard

Completion means all plan items are implemented, pre-existing and newly
introduced worktree issues are fixed, lint/tests/CI are green, the PR exists,
the single final `lavra:lavra-review` has no outstanding actionable findings,
PR comments are resolved, session logging is complete, and the worktree is
clean. Anything less is blocked, not done.
