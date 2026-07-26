#!/usr/bin/env python3
"""Collect bounded, read-only evidence for interrupted Claude/Codex work lanes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

SKIP_DIRS = {
    ".cache",
    ".git",
    ".gradle",
    ".next",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
PRIMARY_BRANCHES = {"main", "master", "trunk", "develop"}
SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(authorization|api[_-]?key|token|password|secret)\b(\s*[:=]\s*)\S+"
    ),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\b(?:gh[pousr]_|sk-|xox[baprs]-)[A-Za-z0-9_-]{8,}"),
)
WORKTREE_PATH = re.compile(
    r"(?:/[A-Za-z0-9._-]+)+/(?:\.worktrees|worktrees)/[A-Za-z0-9._/-]+"
)


def redact(value: str, limit: int = 900) -> str:
    text = " ".join(value.replace("\x00", "").split())
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}<redacted>"
                if match.lastindex == 2
                else "<redacted>"
            ),
            text,
        )
    return text[:limit]


def iso_from_epoch(value: float) -> str:
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).isoformat()


def iter_text(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_text(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "text",
                "content",
                "message",
                "summary",
                "prompt",
                "description",
            }:
                yield from iter_text(item)


def content_text(value: Any) -> str:
    return redact(" ".join(iter_text(value)))


def parse_json_lines(path: Path, tool: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "tool": tool,
        "path": str(path),
        "session_id": path.stem,
        "cwd": None,
        "started_at": None,
        "last_event_at": None,
        "modified_at": iso_from_epoch(path.stat().st_mtime),
        "git": {},
        "last_user_excerpt": None,
        "last_assistant_excerpt": None,
        "plan_events": [],
        "agent_events": [],
        "worktree_paths_mentioned": [],
        "parse_errors": 0,
    }
    mentioned: set[str] = set()
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    record["parse_errors"] += 1
                    continue
                timestamp = item.get("timestamp") or item.get("created_at")
                if timestamp:
                    record["started_at"] = record["started_at"] or timestamp
                    record["last_event_at"] = timestamp
                if item.get("sessionId"):
                    record["session_id"] = item["sessionId"]
                if item.get("cwd"):
                    record["cwd"] = item["cwd"]
                payload = (
                    item.get("payload") if isinstance(item.get("payload"), dict) else {}
                )
                if item.get("type") == "session_meta":
                    record["session_id"] = payload.get("id") or record["session_id"]
                    record["cwd"] = payload.get("cwd") or record["cwd"]
                    record["git"] = payload.get("git") or record["git"]
                message = (
                    item.get("message") if isinstance(item.get("message"), dict) else {}
                )
                role = message.get("role")
                text = content_text(message.get("content"))
                if item.get("type") == "user" or role == "user":
                    record["last_user_excerpt"] = text or record["last_user_excerpt"]
                if item.get("type") == "assistant" or role == "assistant":
                    record["last_assistant_excerpt"] = (
                        text or record["last_assistant_excerpt"]
                    )
                if item.get("type") == "response_item":
                    response_role = payload.get("role")
                    response_text = content_text(payload.get("content"))
                    if response_role == "user":
                        record["last_user_excerpt"] = (
                            response_text or record["last_user_excerpt"]
                        )
                    elif response_role == "assistant":
                        record["last_assistant_excerpt"] = (
                            response_text or record["last_assistant_excerpt"]
                        )
                scan_tool_events(item, path, line_number, record)
                for match in WORKTREE_PATH.findall(line):
                    mentioned.add(match)
    except OSError as error:
        record["read_error"] = str(error)
    record["worktree_paths_mentioned"] = sorted(mentioned)
    record["plan_events"] = record["plan_events"][-5:]
    record["agent_events"] = record["agent_events"][-12:]
    return record


def scan_tool_events(
    item: dict[str, Any], path: Path, line_number: int, record: dict[str, Any]
) -> None:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    candidates: list[tuple[str | None, Any]] = []
    if payload.get("type") in {"function_call", "custom_tool_call"}:
        candidates.append(
            (payload.get("name"), payload.get("arguments") or payload.get("input"))
        )
    message = item.get("message") if isinstance(item.get("message"), dict) else {}
    blocks = message.get("content") if isinstance(message.get("content"), list) else []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            candidates.append((block.get("name"), block.get("input")))
    for name, arguments in candidates:
        if not name:
            continue
        normalized = name.rsplit(".", 1)[-1]
        event = {
            "name": name,
            "source": f"{path}:{line_number}",
            "arguments_excerpt": redact(
                json.dumps(arguments, sort_keys=True, default=str), 1200
            ),
        }
        if normalized in {"update_plan", "TodoWrite", "TaskCreate", "TaskUpdate"}:
            record["plan_events"].append(event)
        if normalized in {
            "spawn_agent",
            "send_message",
            "followup_task",
            "Task",
            "Agent",
            "TaskOutput",
        }:
            record["agent_events"].append(event)


def run_git(
    path: Path, *args: str, check: bool = False
) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(path), *args]
    try:
        return subprocess.run(
            command,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        if check:
            raise
        return subprocess.CompletedProcess(command, 124, "", str(error))


def discover_git_roots(
    workspace: Path, session_cwds: Iterable[str | None]
) -> tuple[list[Path], list[str]]:
    candidates: set[Path] = set()
    errors: list[str] = []
    if workspace.is_dir():
        for current, dirs, files in os.walk(workspace):
            current_path = Path(current)
            relative_depth = len(current_path.relative_to(workspace).parts)
            has_git_directory = ".git" in dirs
            has_git_file = ".git" in files
            if has_git_directory or has_git_file:
                candidates.add(current_path)
            dirs[:] = [
                name
                for name in dirs
                if name not in SKIP_DIRS and not name.startswith(".cache")
            ]
            if relative_depth >= 5:
                dirs[:] = []
    for cwd in session_cwds:
        if not cwd:
            continue
        candidate = Path(cwd).expanduser()
        if not candidate.exists():
            continue
        result = run_git(candidate, "rev-parse", "--show-toplevel")
        if result.returncode == 0:
            candidates.add(Path(result.stdout.strip()))
    common_roots: dict[str, Path] = {}
    for candidate in sorted(candidates):
        result = run_git(
            candidate, "rev-parse", "--path-format=absolute", "--git-common-dir"
        )
        if result.returncode != 0:
            errors.append(f"{candidate}: {redact(result.stderr)}")
            continue
        common_roots.setdefault(result.stdout.strip(), candidate)
    return sorted(common_roots.values()), errors


def default_base(path: Path) -> str | None:
    symbolic = run_git(
        path, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"
    )
    if symbolic.returncode == 0:
        return symbolic.stdout.strip()
    for candidate in ("origin/main", "origin/master", "main", "master"):
        if run_git(path, "rev-parse", "--verify", "--quiet", candidate).returncode == 0:
            return candidate
    return None


def parse_worktree_porcelain(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    row: dict[str, str] = {}
    for line in output.splitlines() + [""]:
        if not line:
            if row:
                rows.append(row)
                row = {}
            continue
        key, _, value = line.partition(" ")
        row[key] = value
    return rows


def inspect_worktree(
    path: Path, branch: str | None, base: str | None
) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "branch": branch,
            "head": None,
            "base": base,
            "upstream": None,
            "status_headers": [],
            "dirty_files": [],
            "recent_commits": [],
            "unique_commits_vs_base": None,
            "changed_files_vs_base": [],
            "merged_into_base": None,
            "inspection_error": "worktree path does not exist; it may be prunable",
        }
    status = run_git(path, "status", "--porcelain=v2", "--branch")
    dirty = run_git(path, "status", "--porcelain")
    recent = run_git(
        path, "log", "-5", "--date=iso-strict", "--pretty=format:%H%x09%ad%x09%s"
    )
    upstream = run_git(
        path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    head = run_git(path, "rev-parse", "HEAD")
    row: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "branch": branch,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "base": base,
        "upstream": upstream.stdout.strip() if upstream.returncode == 0 else None,
        "status_headers": [
            line for line in status.stdout.splitlines() if line.startswith("# ")
        ],
        "dirty_files": [redact(line, 500) for line in dirty.stdout.splitlines()[:100]],
        "recent_commits": recent.stdout.splitlines(),
        "unique_commits_vs_base": None,
        "changed_files_vs_base": [],
        "merged_into_base": None,
    }
    if base and head.returncode == 0:
        count = run_git(path, "rev-list", "--count", f"{base}..HEAD")
        if count.returncode == 0:
            row["unique_commits_vs_base"] = int(count.stdout.strip())
        changed = run_git(path, "diff", "--name-only", f"{base}...HEAD")
        if changed.returncode == 0:
            row["changed_files_vs_base"] = changed.stdout.splitlines()[:200]
        merged = run_git(path, "merge-base", "--is-ancestor", "HEAD", base)
        row["merged_into_base"] = merged.returncode == 0
    return row


def inspect_repositories(roots: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    repositories: list[dict[str, Any]] = []
    errors: list[str] = []
    for root in roots:
        base = default_base(root)
        worktrees = run_git(root, "worktree", "list", "--porcelain")
        if worktrees.returncode != 0:
            errors.append(f"{root}: {redact(worktrees.stderr)}")
            continue
        inspected: list[dict[str, Any]] = []
        for entry in parse_worktree_porcelain(worktrees.stdout):
            worktree_path = Path(entry["worktree"])
            branch = entry.get("branch", "").removeprefix("refs/heads/") or None
            inspected.append(inspect_worktree(worktree_path, branch, base))
        remote = run_git(root, "remote", "get-url", "origin")
        repositories.append(
            {
                "root": str(root),
                "origin": remote.stdout.strip() if remote.returncode == 0 else None,
                "default_base": base,
                "worktrees": inspected,
            }
        )
    return repositories, errors


def correlate(
    sessions: list[dict[str, Any]], repositories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    worktrees = [row for repo in repositories for row in repo["worktrees"]]
    lanes: dict[str, dict[str, Any]] = {}

    def ensure_lane(key: str, worktree: dict[str, Any] | None) -> dict[str, Any]:
        return lanes.setdefault(
            key,
            {
                "worktree": worktree,
                "session_refs": [],
                "signals": [],
            },
        )

    for session in sessions:
        cwd = session.get("cwd")
        matches: list[tuple[dict[str, Any], str]] = []
        if cwd:
            cwd_path = Path(cwd)
            cwd_matches = [
                row
                for row in worktrees
                if cwd_path == Path(row["path"])
                or Path(row["path"]) in cwd_path.parents
            ]
            if cwd_matches:
                matches.append(
                    (max(cwd_matches, key=lambda row: len(row["path"])), "cwd")
                )
        for mentioned in session.get("worktree_paths_mentioned", []):
            mentioned_path = Path(mentioned)
            path_matches = [
                row
                for row in worktrees
                if mentioned_path == Path(row["path"])
                or Path(row["path"]) in mentioned_path.parents
            ]
            if path_matches:
                matches.append(
                    (max(path_matches, key=lambda row: len(row["path"])), "transcript")
                )
        if not matches:
            matches.append((None, "unmapped_session"))
        seen_keys: set[str] = set()
        for match, reason in matches:
            key = (
                match["path"]
                if match
                else f"session:{session['tool']}:{session['session_id']}"
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            lane = ensure_lane(key, match)
            lane["session_refs"].append(
                {
                    "tool": session["tool"],
                    "session_id": session["session_id"],
                    "path": session["path"],
                    "modified_at": session["modified_at"],
                    "match_reason": reason,
                }
            )
    for worktree in worktrees:
        ensure_lane(worktree["path"], worktree)
    for lane in lanes.values():
        worktree = lane["worktree"]
        if worktree:
            if worktree["dirty_files"]:
                lane["signals"].append("dirty_worktree")
            if worktree["branch"] and worktree["branch"] not in PRIMARY_BRANCHES:
                lane["signals"].append("non_primary_branch")
            if worktree["unique_commits_vs_base"]:
                lane["signals"].append("unique_commits")
            if worktree["merged_into_base"] is False:
                lane["signals"].append("not_merged_into_base")
        lane["session_refs"].sort(key=lambda row: row["modified_at"], reverse=True)
    return sorted(
        lanes.values(),
        key=lambda row: (
            row["session_refs"][0]["modified_at"] if row["session_refs"] else ""
        ),
        reverse=True,
    )


def transcript_paths(home: Path, cutoff: float, limit: int) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    roots = (
        (home / ".claude" / "projects", "claude"),
        (home / ".codex" / "sessions", "codex"),
    )
    for root, tool in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                if path.stat().st_mtime >= cutoff:
                    found.append((path, tool))
            except OSError:
                continue
    found.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
    return found[:limit]


def collect(
    workspace: Path, since_hours: float, transcript_limit: int, home: Path
) -> dict[str, Any]:
    now = dt.datetime.now(tz=dt.timezone.utc)
    cutoff = now.timestamp() - since_hours * 3600
    sessions = [
        parse_json_lines(path, tool)
        for path, tool in transcript_paths(home, cutoff, transcript_limit)
    ]
    roots, discovery_errors = discover_git_roots(
        workspace, (session.get("cwd") for session in sessions)
    )
    repositories, git_errors = inspect_repositories(roots)
    return {
        "schema_version": 1,
        "collected_at": now.isoformat(),
        "cutoff": iso_from_epoch(cutoff),
        "workspace": str(workspace),
        "sessions": sessions,
        "repositories": repositories,
        "correlated_lanes": correlate(sessions, repositories),
        "errors": discovery_errors + git_errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "workspace")
    parser.add_argument("--since-hours", type=float, default=72)
    parser.add_argument("--transcript-limit", type=int, default=100)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.since_hours <= 0 or args.transcript_limit <= 0:
        print("--since-hours and --transcript-limit must be positive", file=sys.stderr)
        return 2
    artifact = collect(
        args.workspace.expanduser().resolve(),
        args.since_hours,
        args.transcript_limit,
        Path.home(),
    )
    rendered = json.dumps(artifact, indent=None if args.compact else 2, sort_keys=True)
    if args.output:
        output = args.output.expanduser()
        if output.exists():
            print(f"refusing to overwrite existing output: {output}", file=sys.stderr)
            return 2
        output.write_text(rendered + "\n", encoding="utf-8")
        print(output.resolve())
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
