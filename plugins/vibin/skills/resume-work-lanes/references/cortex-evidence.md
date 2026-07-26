# Cortex evidence routing

Use Cortex as the primary session-discovery and transcript-intelligence layer. Use Git, trackers, and the forge to verify current state.

## Preferred routes

When the local CLI is installed:

```bash
cortex sessions watchstatus --json
cortex sessions projects --since 72h --json
cortex sessions blocks --since 72h --limit 200 --detail compact --json
cortex sessions search update_plan --since 72h --limit 100 --json
cortex sessions search '"remaining work" OR pending OR blocked OR unfinished' --since 72h --limit 100 --json
cortex sessions context /absolute/project/path --limit 100 --json
```

When Cortex is exposed as an MCP tool instead, use these equivalent actions:

| Purpose | MCP action |
|---|---|
| Recent sessions | `sessions` |
| Recent projects | `list_ai_projects` |
| Sessions matching a query | `search_sessions` |
| Project-wide context | `project_context` |
| Time-bucketed activity | `usage_blocks` |
| Tools observed in transcripts | `list_ai_tools` |

Discover the live tool schema before calling it. Do not assume CLI flags map one-to-one to MCP arguments.

For MCP-only environments, use MCP for session evidence and run the bundled collector with `--source git-only`. Do not let a missing local binary trigger raw parsing before checking the connected Cortex tool.

## Interpretation rules

- `projects` identifies candidate project lanes and cross-tool activity.
- `blocks` supplies temporal clustering; it does not mean the lane is blocked.
- `search update_plan` and unfinished-work queries identify candidate sessions. Their snippets are leads, not completion evidence.
- `context` supplies recent entries, session IDs, and canonical transcript paths for a project.
- Count every returned context session ID, but do not trust its order: Cortex project context currently aggregates all history without ordering. Materialize an ID only when it matches transcript metadata modified inside the evidence window, and report unmatched IDs as time-unqualified rather than turning arbitrary historical IDs into lanes.
- Keep text-only search matches under `cortex.search_leads`. They enrich a verified session but never create a lane by themselves.
- Generic `agent`, `Task`, or `spawn_agent` searches often match system instructions. Require task-specific content or live worktree evidence before creating a lane from them.
- Cortex content may be scrubbed. Read the canonical transcript path only for a fact that indexed evidence cannot establish.

## Freshness and fallback

Check `watchstatus.health`:

- require `schema_current: true`;
- treat non-empty `stale_indicators` as stale;
- compare `last_successful_ingest_at` with the interruption window;
- inspect `sessions errors` when freshness is uncertain.

If Cortex is unavailable or stale:

1. Record the failure and use `raw_files_fallback`.
2. Do not claim the Cortex inventory is complete.
3. Do not run `cortex sessions index` in orientation mode; indexing writes Cortex state.
4. If the user authorizes repair, index only the affected path or bounded time window, then rerun Cortex discovery.

Never flatten a search hit into a completed or active lane without live repository verification.

## Portability

The collector requires Python 3.10 or newer. It honors `CLAUDE_CONFIG_DIR` and `CODEX_HOME` for raw fallback roots and recognizes Unix and Windows worktree path forms.

PowerShell example:

```powershell
$laneTmpDir = New-Item -ItemType Directory -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.Guid]::NewGuid()))
python <skill-dir>/scripts/collect_lane_evidence.py --workspace "$HOME/workspace" --since-hours 72 --source auto --progress --output "$laneTmpDir/lane-evidence.json"
```

On Windows, the artifact inherits the ACL of this private, user-owned directory;
the `0600` file-mode guarantee applies only on POSIX.
