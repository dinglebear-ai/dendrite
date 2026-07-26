---
name: resume-work-lanes
description: Reconstruct interrupted parallel Claude and Codex work from recent transcripts, Git worktrees, branches, plans, beads, PRs, and CI; distinguish completed, active, blocked, and stale lanes; identify dependencies and drift; and produce verified lane packets plus an actionable restart order. Use when the user says "get up to speed", "what were all the agents working on", "resume interrupted work", "find every active lane", "pick up after a usage limit", "continue the recent Claude/Codex sessions", or asks to restart multiple agents or worktrees after an interruption.
---

# Resume Work Lanes

Rebuild the state of interrupted multi-agent work from live evidence. Do not assume that a transcript claim, old plan, branch name, or existing worktree proves current status.

## 1. Choose the mode

- **Orient**: inventory lanes and produce the recovery plan. Use by default.
- **Resume**: orient first, then restart approved lanes. Enter this mode only when the user explicitly asks to resume, start, or dispatch the lanes.

Do not mutate repositories, switch branches, clean worktrees, or start agents during orientation.

## 2. Collect the initial evidence

Run the bundled collector from any directory:

```bash
lane_tmp_dir="$(mktemp -d)"
python3 <skill-dir>/scripts/collect_lane_evidence.py \
  --workspace "${WORKSPACE_ROOT:-$HOME/workspace}" \
  --since-hours 72 \
  --output "$lane_tmp_dir/lane-evidence.json"
```

Use a longer window when the interruption is older. The collector is read-only except for an explicitly requested output file. It emits:

- recent Claude and Codex transcript metadata and bounded excerpts;
- plan, agent, and tool events useful for locating unfinished work;
- every discoverable Git worktree with branch, HEAD, upstream, dirty state, unique commits, and changed files;
- correlations between sessions and worktrees;
- collection errors instead of silently dropping uncertain evidence.

Read the JSON artifact. Treat it as triage evidence, not the final answer.

## 3. Identify candidate lanes

Include a lane when one or more of these are observed:

- a recent session cwd maps to a worktree or repository;
- a recent plan or agent event names a distinct task;
- a non-primary worktree is dirty, ahead, unmerged, or attached to an open PR;
- a session ended with unfinished plan items, a blocking error, a pending tool call, or a handoff;
- a completed implementation still lacks verification, push, review, merge, deploy, or cleanup.

Do not treat these as active lanes without more evidence:

- protected long-lived worktrees documented by repository policy;
- clean primary branches with no incomplete recent session;
- merged or deleted branches whose cleanup is already complete;
- old session files that have been superseded by a newer session on the same goal.

Separate one session containing several independent agent tasks into several lanes. Combine multiple sessions only when they clearly continue the same goal in the same implementation line.

## 4. Verify each lane

For every candidate lane:

1. Read the repository's `CLAUDE.md` before interpreting branch or worktree state.
2. Re-run live Git status in the exact worktree. Record branch, HEAD, upstream, ahead/behind, dirty files, recent commits, and diff against the intended base.
3. Read enough of the relevant transcript files to recover:
   - the user goal and scope changes;
   - the last explicit plan and its statuses;
   - subagent task assignments and returned results;
   - files claimed changed and commands claimed run;
   - blockers, failures, open questions, and the last promised next action.
4. Verify claims against files, diffs, commits, tests, and generated artifacts. A transcript saying "done" is not proof.
5. Check repository-native trackers and plans when present. Use `bd` for Beads repositories and inspect `docs/plans`, `.claude/current-plan`, or equivalent live artifacts.
6. Check the forge when configured: open PR, review state, check runs, merge state, and whether the branch still exists remotely.
7. Record drift between the interrupted session and now. Never paper over moved HEADs, changed bases, new commits, resolved blockers, or deleted worktrees.

Bound expensive reads. Start with transcript tails and targeted searches; expand to the full transcript only when required to establish a fact.

## 5. Classify lane state

Use exactly one state:

- `active_incomplete`: useful work exists and concrete implementation remains.
- `blocked`: work cannot proceed until a named dependency, decision, permission, or external state changes.
- `completed_unlanded`: implementation and required verification are complete, but push/review/merge/deploy remains.
- `landed_needs_closeout`: work landed, but sync, cleanup, deployment verification, tracker updates, or handoff remains.
- `completed`: the goal and required closeout are proven complete.
- `protected_long_lived`: repository policy says the branch/worktree intentionally persists.
- `unknown`: evidence is insufficient or contradictory.

State confidence as `high`, `medium`, or `low` and cite the evidence that controls the classification.

## 6. Build the restart plan

Read [references/report-template.md](references/report-template.md) and use its report shape.

Order lanes by:

1. blockers that unlock other lanes;
2. nearly complete landing/closeout work;
3. foundational shared changes;
4. independent implementation lanes;
5. cleanup only after dependent work is safe.

Call out overlapping files, shared migrations, branch ancestry, deploy dependencies, and resource contention. Mark lanes as parallel only when they can run independently.

For every non-complete lane, produce a restart packet containing:

- exact worktree and branch;
- verified objective and current state;
- completed implementation with evidence;
- remaining checklist;
- first command or file inspection;
- required tests and completion gate;
- dependencies and forbidden scope;
- transcript, plan, bead, PR, and CI references.

## 7. Resume only with authority

If the user explicitly requested resume mode:

1. Present the inventory and restart order first.
2. Preserve dirty and unmerged worktrees.
3. Reuse the existing worktree when safe; create a new one only when the prior path is missing or unsafe.
4. Start replacement agents only when the environment permits delegation and the user's request authorizes it. Old in-memory agents cannot be resumed.
5. Give each agent one bounded lane packet. Do not leak conclusions from unrelated lanes.
6. Track every restarted lane and report whether it is running, blocked, or completed.

If authorization is orientation-only, end by asking which lanes to activate. Do not start work implicitly.

## Quality rules

- Prefer live repository and forge evidence over transcript recollection.
- Preserve unrelated dirt and protected worktrees.
- Distinguish planned, attempted, implemented, verified, pushed, merged, deployed, and cleaned up.
- Cite paths, SHAs, PRs, run IDs, plan items, and session IDs.
- Label unknowns; never turn absence of evidence into completion.
- Redact credentials and private message content from reports.
- Keep the executive summary concise while making every restart packet executable.
