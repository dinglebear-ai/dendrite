---
date: 2026-06-18 02:12:55 EST
repo: git@github.com:jmagar/dendrite.git
branch: main
head: ed43890
session id: f46cb437-b311-4c86-bc10-cac2eef7644d
transcript: /home/jmagar/.claude/projects/-home-jmagar-workspace-dendrite/f46cb437-b311-4c86-bc10-cac2eef7644d.jsonl
working directory: /home/jmagar/workspace/dendrite
worktree: /home/jmagar/workspace/dendrite ed43890 [main]
---

# Dendrite marketplace and no-MCP variant session

> **Superseded 2026-07-28.** The no-MCP marketplace variant described below has
> been retired fleet-wide. The `marketplace-no-mcp` branch, its sync and drift
> workflows, the `apply-no-mcp-marketplace` / `check-no-mcp-drift` scripts, and
> `docs/no-mcp-variant.md` are all gone; `main` is the only published
> marketplace branch. This log is kept as a dated historical record — do not
> treat any policy in it as current.

## User Request

The session started as a broad Dendrite plugin and skill maintenance pass: review skills, remove or relocate duplicated skills, add missing docs, create Gemini extension manifests, and update Rust/rmcp guidance. Later requests narrowed to keeping a `marketplace-no-mcp` branch/ref around for installs where MCP servers are already provided by the Labby gateway, documenting that policy across repos, and saving this session.

## Session Overview

- Reviewed and updated Dendrite plugin/skill content, including the new `vibin/worktree-setup` skill and marketplace inventory.
- Committed and pushed Dendrite main changes in `c323663`, `c9fc245`, and `ed43890`.
- Created and pushed `marketplace-no-mcp` refs across the relevant repos: `lumen`, `axon`, `rarcane`, `rtemplate-mcp`, `lab`, `ytdl-mcp`, and `dendrite`.
- Added `CLAUDE.md` notes in sibling repos explaining that `marketplace-no-mcp` is a long-lived alternate marketplace ref, not stale branch cleanup.
- Preserved unrelated dirty work in sibling repos and avoided sweeping it into documentation commits.

## Sequence of Events

1. Reviewed and cleaned up Dendrite plugin/skill inventory, including duplicate and near-duplicate skill/plugin boundaries.
2. Removed/relocated requested content, including removing the `creating-snippets` skill from Dendrite and moving it under Labby, removing the summarize skill, and removing the retired SWAG MCP marketplace entries.
3. Added missing `README.md` / `CHANGELOG.md` artifacts, generated Gemini extension manifests, and updated Dendrite inventory docs.
4. Added and reviewed new plugin/skill surfaces including `zsnoop-mcp`, `create-swag-config`, `monolith-check`, and the new `vibin/worktree-setup` skill.
5. Pulled the latest Dendrite safely, using a clean review worktree because the main checkout had unrelated dirty work.
6. Dispatched a skill reviewer agent for `vibin/worktree-setup`, integrated its findings, rebased the review branch, then cherry-picked the hardening fixes onto `main`.
7. Committed and pushed Dendrite marketplace and skill updates on `main`.
8. Created, rebased, and pushed `marketplace-no-mcp` branches across repos so no-MCP marketplace refs exist remotely.
9. Documented the `marketplace-no-mcp` policy in Dendrite and sibling repo `CLAUDE.md` files, committing and pushing only the requested documentation changes.
10. Ran the `vibin:save-to-md` maintenance pass and generated this session artifact.

## Key Findings

- `marketplace-no-mcp` is an intentional long-lived alternate marketplace ref, not a merge-ready feature branch; Dendrite records this in `CLAUDE.md:29` and `README.md:22`.
- Dendrite `main` is clean and synced with `origin/main` at `ed43890`.
- Dendrite has three worktrees: `main`, `marketplace-no-mcp`, and `codex/review-worktree-setup-skill`; only `marketplace-no-mcp` is intentional long-lived policy.
- No Dendrite beads were present: `bd list --all --sort updated --reverse --limit 100 --json` returned `[]`, and `.beads/interactions.jsonl` was absent.
- The injected Claude transcript path exists, but it contains only 42 JSONL lines of bridge/session metadata rather than a full implementation transcript.

## Technical Decisions

- Kept `marketplace-no-mcp` as a separate branch/ref instead of merging into `main` because `main` is the canonical full marketplace and the no-MCP branch is an install variant.
- Used clean worktrees for risky review/rebase work so the dirty Dendrite checkout was not overwritten during pull/review.
- Used path-limited commits when saving session documentation and when committing cross-repo `CLAUDE.md` notes, preserving unrelated dirty work.
- Left Dendrite's old review worktree/branch in place because its ancestry/diff was not simple enough to prove safe for automatic deletion during the documentation pass.
- Chose not to force-push any branch; all pushes were normal pushes after rebase or direct commit.

## Files Changed

| status | path | previous path | purpose | evidence |
|---|---|---|---|---|
| modified | `CLAUDE.md` | - | Documented `marketplace-no-mcp` as a long-lived branch in Dendrite. | Commit `ed43890`; `CLAUDE.md:29`. |
| modified | `README.md` | - | Added Marketplace Variants docs and regenerated inventory. | Commits `c323663`, `ed43890`; `README.md:22`, `README.md:39`. |
| modified | `.agents/plugins/marketplace.json` | - | Synchronized Codex/OpenAI marketplace entries. | Commit `c323663`. |
| modified | `.claude-plugin/marketplace.json` | - | Synchronized Claude marketplace entries. | Commit `c323663`. |
| deleted | `plugins/acp/.mcp.json` | - | Removed bundled MCP registration for no-MCP/gateway-oriented packaging cleanup. | Commit `c323663`. |
| deleted | `plugins/agent-os/.mcp.json` | - | Removed bundled MCP registration from Dendrite main cleanup. | Commit `c323663`. |
| deleted | `plugins/dozzle/.mcp.json` | - | Removed bundled MCP registration from Dendrite main cleanup. | Commit `c323663`. |
| deleted | `plugins/swag/.mcp.json` | - | Removed retired SWAG MCP packaging from Dendrite. | Commit `c323663`. |
| deleted | `plugins/vibin/.mcp.json` | - | Removed bundled MCP registration from Dendrite main cleanup. | Commit `c323663`. |
| deleted | `plugins/zsnoop-mcp/.mcp.json` | - | Removed bundled MCP registration from Dendrite main cleanup. | Commit `c323663`. |
| created | `plugins/testing/skills/mcpjam-ui-testing/references/axon.md` | - | Added MCPJam/Axon reference material. | Commit `c323663`. |
| created | `plugins/vibin/skills/monolith-check/` | - | Added the `monolith-check` skill and scripts. | Commit `c323663`. |
| modified | `plugins/vibin/skills/worktree-setup/README.md` | - | Clarified manifest safety and worktree sync behavior. | Commit `c9fc245`. |
| modified | `plugins/vibin/skills/worktree-setup/references/minimal-worktree-setup.sh` | - | Made trust-command failures non-fatal. | Commit `c9fc245`. |
| modified | `plugins/vibin/skills/worktree-setup/scripts/worktree-rm.sh` | - | Fixed shellcheck issues and safer control flow. | Commit `c9fc245`. |
| modified | `plugins/vibin/skills/worktree-setup/scripts/worktree-sync.sh` | - | Hardened manifest path handling and trust checks. | Commit `c9fc245`. |
| modified | `plugins/vibin/skills/worktree-setup/tests/smoke.sh` | - | Cleaned lint issues while preserving smoke coverage. | Commit `c9fc245`. |
| modified | many plugin skill, manifest, hook, script, and companion files | - | Broader Dendrite plugin catalog/userConfig/Gemini/skill updates. | `git show --stat c323663` lists 133 changed files. |
| modified | sibling repo `CLAUDE.md` files | - | Documented `marketplace-no-mcp` policy in `lumen`, `axon`, `rustcane`, `rmcp-template`, `lab`, and `ytdl-mcp`. | Commits `a1c13ca`, `f9ef852b`, `eb82e14`, `dbac1c3`, `b5cfe260`, `92de5a6`. |
| created | `docs/sessions/2026-06-18-dendrite-marketplace-no-mcp-session.md` | - | Saved this session artifact. | Current save-to-md run. |

## Beads Activity

No bead activity observed in Dendrite. Evidence: `bd list --all --sort updated --reverse --limit 100 --json` returned `[]`; `tail -200 .beads/interactions.jsonl` returned `none`.

## Repository Maintenance

### Plans

- Checked `docs/plans` with `find docs/plans -maxdepth 2 -type f`; no plan files were found.
- No completed plans were moved, and `docs/plans/complete/` was not created.

### Beads

- Checked Beads state with `bd list --all --sort updated --reverse --limit 100 --json`; no issues were present.
- No beads were created, edited, assigned, claimed, commented on, or closed.

### Worktrees and branches

- Inspected `git worktree list --porcelain`, local branches, and remote branches.
- Left `/home/jmagar/workspace/_no_mcp_worktrees/dendrite` in place because `marketplace-no-mcp` is an intentional long-lived alternate marketplace ref.
- Left `/home/jmagar/workspace/_review_worktrees/dendrite-latest` in place because `codex/review-worktree-setup-skill` was not proven safe for automatic deletion during this maintenance pass.
- Left `origin/claude/available-skills-w6p7jm` and `origin/codex/dendrite-gemini-skill-marketplace` untouched because remote branch ownership and cleanup intent were not part of this request.

### Stale docs

- Reviewed the docs directly contradicted by the new no-MCP branch policy.
- Updated Dendrite `CLAUDE.md` and `README.md` earlier in the session; verified `rg -n "marketplace-no-mcp|Long-Lived Branches|Marketplace Variants" CLAUDE.md README.md`.
- Updated sibling repo `CLAUDE.md` files with the same policy and pushed those changes.

### Transparency

- No destructive cleanup was performed during the save pass.
- The only new file from this pass is this session artifact, which is committed separately by path.

## Tools and Skills Used

- **Skills.** Used `vibin:repo-status` to gather branch/worktree status and `vibin:save-to-md` to create this artifact.
- **Subagents.** Dispatched a skill reviewer agent for `plugins/vibin/skills/worktree-setup`; the agent reported documentation and shell-script safety findings that were integrated.
- **Shell and Git.** Used `git status`, `git worktree list`, `git rebase`, `git cherry-pick`, `git commit`, `git push`, `git show`, `git diff`, `git stash`, `git ls-remote`, and `git branch` to manage and verify changes.
- **Validation tools.** Used `jq`, `plugins/scripts/generate-readme-inventory`, `bash -n`, `shellcheck`, Dendrite convention loops, and the `worktree-setup` smoke test.
- **External CLIs.** Used `gh pr view` to check PR context, `bd` to inspect Beads, and repo-local hooks including Axon's `lefthook` pre-push pipeline.
- **MCP/plugin config tooling.** Used local plugin configuration surfaces indirectly; developer setup messages reported several plugin config files written under `~/.config/lab-*`.

## Commands Executed

| command | result |
|---|---|
| `git pull --ff-only` | Fast-forwarded Dendrite main to include the new `worktree-setup` commits before preserving/reapplying WIP. |
| `git stash push -u -m ...` / `git stash apply stash@{0}` | Preserved and reapplied dirty Dendrite work before committing. A safety stash remained during the session. |
| `plugins/scripts/generate-readme-inventory --check --strict` | Initially detected README inventory drift; passed after regeneration. |
| `jq empty .claude-plugin/marketplace.json .agents/plugins/marketplace.json` | Verified marketplace manifests parsed. |
| `bash -n ...worktree-setup...` | Verified worktree scripts parsed. |
| `shellcheck ...worktree-setup...` | Found shell issues after rebase; passed after fixes. |
| `plugins/vibin/skills/worktree-setup/tests/smoke.sh` | Passed all smoke checks for worktree setup, sync, check, init, submodule, and removal behavior. |
| `git push origin main` | Pushed Dendrite commits `c323663`, `c9fc245`, and `ed43890`. |
| `git push origin marketplace-no-mcp` / `git push fork marketplace-no-mcp` | Pushed no-MCP refs across Dendrite, Axon, rarcane, rtemplate-mcp, Lab, ytdl-mcp, and Lumen. |
| `git push` in sibling repos | Pushed `CLAUDE.md` no-MCP policy commits for Axon, rustcane, rmcp-template, Lab, ytdl-mcp, and Lumen fork main. |

## Errors Encountered

- **Dirty checkout prevented a direct pull.** The main Dendrite checkout had large WIP, so the first review used a clean worktree and later used an explicit stash before fast-forwarding `main`.
- **Dendrite review branch rebase conflicts.** Rebasing `codex/review-worktree-setup-skill` onto updated `origin/main` conflicted in `worktree-setup` docs/scripts. Resolution kept upstream's larger implementation and re-applied manifest hardening.
- **Dendrite no-MCP rebase conflicts.** Rebasing `marketplace-no-mcp` conflicted in `plugins/agent-os/gemini-extension.json` and `plugins/dozzle/gemini-extension.json`. Resolution kept current metadata while removing bundled MCP server registrations.
- **Shellcheck failures after rebase.** `worktree-sync.sh`, `worktree-rm.sh`, and the smoke script had fragile `A && B || C` patterns and a trap false positive. These were patched and rechecked.
- **Incorrect verification loop.** A zsh tuple-splitting mistake checked the wrong repository path while verifying no-MCP refs. It was rerun with an explicit Bash function and remote/local SHA comparisons passed.
- **Long Axon hooks.** Axon pre-push hooks ran web build, clippy, and 3166 tests twice; both completed successfully after waiting.

## Behavior Changes (Before/After)

| area | before | after |
|---|---|---|
| Dendrite marketplace docs | No clear documented distinction between `main` and `marketplace-no-mcp`. | `CLAUDE.md` and `README.md` document `main` as the full marketplace and `marketplace-no-mcp` as the no-MCP alternate ref. |
| no-MCP refs | Several no-MCP branches existed only locally or were behind. | All requested no-MCP refs were pushed and verified remote/local SHA matched. |
| Worktree setup skill | Manifest copy/link paths could be less constrained and shell scripts had lint issues. | Manifest paths are constrained to relative git-ignored entries; smoke/lint checks pass. |
| Dendrite plugin catalog | Dirty WIP included marketplace/plugin/skill updates and inventory drift. | Main was committed and pushed with regenerated inventory and synced marketplace manifests. |
| Sibling repo memory | Sibling repos did not consistently document the no-MCP branch policy. | `CLAUDE.md` in each relevant repo now documents the branch policy. |

## Verification Evidence

| command | expected | actual | status |
|---|---|---|---|
| `jq empty .claude-plugin/marketplace.json .agents/plugins/marketplace.json` | Marketplace JSON parses. | Passed with no output. | pass |
| `plugins/scripts/generate-readme-inventory --check --strict` | README inventory matches generated state. | Failed before regeneration, passed after. | pass |
| `test ! -e plugins/labby` plus OpenAI companion loop | No local Labby plugin and every skill has `agents/openai.yaml`. | Passed with no output. | pass |
| `bash -n` on worktree setup scripts | Shell scripts parse. | Passed with no output. | pass |
| `shellcheck` on worktree setup scripts | No shellcheck findings. | Passed after fixes. | pass |
| `plugins/vibin/skills/worktree-setup/tests/smoke.sh` | Worktree setup behavior passes smoke tests. | `ALL SMOKE TESTS PASSED`. | pass |
| Axon pre-push hook | Version sync, web build, clippy, tests pass. | Web build, clippy, and 3166 tests passed. | pass |
| remote/local SHA check for no-MCP refs | Remote and local branch SHAs match. | All checked refs reported `OK pushed`. | pass |

## Risks and Rollback

- The broad Dendrite marketplace commit `c323663` touched 133 files; rollback path is `git revert c323663` followed by targeted reapplication of any desired subsets.
- The no-MCP refs are intentionally separate; if an install should use bundled MCP server registrations, use `main`, not `marketplace-no-mcp`.
- Sibling repos still have unrelated dirty work; those changes were preserved and are not part of the Dendrite session-log commit.
- The old Dendrite review worktree may be cleaned later after comparing it against pushed `main`; it was left alone to avoid unsafe deletion.

## Decisions Not Taken

- Did not merge `marketplace-no-mcp` into `main`; that would erase the distinction between full and no-MCP marketplace installs.
- Did not force-delete Dendrite's `codex/review-worktree-setup-skill` branch/worktree during the save pass because it was not proven safe.
- Did not force-push any repository branch.
- Did not commit unrelated sibling-repo dirty work when adding `CLAUDE.md` notes.

## References

- `CLAUDE.md:29` — Dendrite long-lived branch policy.
- `README.md:22` — Dendrite marketplace variant documentation.
- `plugins/vibin/skills/worktree-setup/SKILL.md:2` — New `worktree-setup` skill.
- Commit `c323663` — broad marketplace and skill sync.
- Commit `c9fc245` — `worktree-setup` hardening.
- Commit `ed43890` — Dendrite no-MCP documentation.
- Sibling repo docs commits: `a1c13ca`, `f9ef852b`, `eb82e14`, `dbac1c3`, `b5cfe260`, `92de5a6`.

## Open Questions

- Whether to remove the stale-looking Dendrite `codex/review-worktree-setup-skill` worktree/branch after a separate explicit cleanup pass.
- Whether to open pull requests for the no-MCP variant branches or treat branch refs alone as the distribution mechanism.
- Whether the safety stash from the earlier Dendrite pull is still needed; it was not inspected or dropped during this save pass.

## Next Steps

- Use `marketplace-no-mcp` refs when adding marketplaces for environments where MCP servers are already provided by Labby.
- Perform a dedicated Dendrite branch cleanup pass if the old review branch/worktree should be removed.
- Continue any unrelated dirty work in sibling repos from their existing worktrees; it was intentionally preserved.
- If installing Claude Code from the no-MCP Dendrite marketplace, first purge old full-marketplace plugin entries from Claude config and then add the no-MCP marketplace ref.
