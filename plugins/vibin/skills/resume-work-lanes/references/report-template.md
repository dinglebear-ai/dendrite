# Lane recovery report

Use this shape. Omit empty optional sections, but never omit uncertainty or blockers.

## Recovery summary

- Evidence window: `<start> to <end>`
- Session source: `<Cortex primary | raw-file fallback and reason>`
- Cortex health: `<healthy | stale/unavailable with exact indicators>`
- Sessions inspected: `<count and tools>`
- Repositories/worktrees inspected: `<count>`
- Active lanes: `<count>`
- Recommended parallelism: `<count and reason>`
- Global blocker: `<none or exact blocker>`

## Coverage and limitations

- Cortex calls: `<successful and failed calls>`
- Projects: `<discovered / context-inspected / omitted>`
- Sessions: `<enumerated / evidence-inspected / inventory-only>`
- Truncation: `<search, context, raw fallback, repository limits>`
- Collector errors: `<every error or none>`
- Git freshness: `<local-ref snapshot; forge checks completed or pending>`
- Trackers/forge verified: `<yes with scope | no>`

Do not call the inventory complete when any required call failed, a truncation flag is true, or an inventory-only session remains unresolved.

## Lane inventory

| Lane | Repo/worktree | Branch | State | Confidence | Controlling evidence | Next gate |
|---|---|---|---|---|---|---|

List protected long-lived and completed lanes too, so they are not rediscovered as unfinished work.

## Drift since interruption

- `<lane>`: `<old state>` -> `<current observed state>`

## Dependencies and restart order

1. `<lane or prerequisite>` - `<why first>`
2. `<parallel group>` - `<why safe in parallel>`

State file overlap, ancestry, migration, deployment, review, and resource dependencies.

## Restart packet: `<lane name>`

- **State / confidence:** `<classification>` / `<high|medium|low>`
- **Worktree / branch / HEAD:** `<absolute path>` / `<branch>` / `<sha>`
- **Objective:** `<verified user goal>`
- **Implemented:** `<facts with file, diff, or commit evidence>`
- **Verified:** `<commands or CI runs and their results>`
- **Still required:**
  - [ ] `<concrete step>`
- **First move:** `<exact command or file inspection>`
- **Completion gate:** `<tests, review, merge, deploy, or cleanup required>`
- **Dependencies:** `<lane, decision, permission, or none>`
- **Scope guardrails:** `<what this lane must not touch>`
- **Sources:** `<session ids and paths, plan, bead, PR, CI run>`

## Proposed activation

| Wave | Lane | Execution | Reason |
|---|---|---|---|

End with one of:

- Orientation mode: `Ready to activate these lanes in the proposed waves?`
- Resume mode: `Activated <lanes>; <blocked lanes> remain blocked on <reasons>.`
