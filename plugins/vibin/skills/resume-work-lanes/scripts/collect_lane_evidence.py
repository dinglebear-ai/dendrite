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
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
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
WINDOWS_WORKTREE_PATH = re.compile(
    r"[A-Za-z]:\\(?:[^\\\r\n\"']+\\)*(?:\.worktrees|worktrees)\\[^\\\r\n\"']+"
)
CORTEX_SEARCH_QUERIES = {
    "plans": "update_plan OR TodoWrite",
    "unfinished": '"remaining work"',
}
VERIFIED_PLAN_EVENT = re.compile(
    r"^\[function_call (?:functions\.)?(?:update_plan|TodoWrite)\]$"
)
UUID_SUFFIX = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.IGNORECASE,
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


def mentioned_worktree_paths(value: str) -> list[str]:
    return WORKTREE_PATH.findall(value) + WINDOWS_WORKTREE_PATH.findall(value)


def sanitize_origin(value: str) -> str:
    return re.sub(r"(://)[^/@\s]+@", r"\1<redacted>@", redact(value, 1200))


def parse_json_lines(
    path: Path, tool: str, deadline: float | None = None
) -> dict[str, Any]:
    try:
        modified_at = iso_from_epoch(path.stat().st_mtime)
    except OSError as error:
        return {
            "tool": tool,
            "path": str(path),
            "session_id": path.stem,
            "cwd": None,
            "started_at": None,
            "last_event_at": None,
            "modified_at": None,
            "git": {},
            "last_user_excerpt": None,
            "last_assistant_excerpt": None,
            "recent_excerpt": None,
            "search_hits": [],
            "plan_events": [],
            "agent_events": [],
            "worktree_paths_mentioned": [],
            "parse_errors": 0,
            "read_error": str(error),
        }
    record: dict[str, Any] = {
        "tool": tool,
        "path": str(path),
        "session_id": path.stem,
        "cwd": None,
        "started_at": None,
        "last_event_at": None,
        "modified_at": modified_at,
        "git": {},
        "last_user_excerpt": None,
        "last_assistant_excerpt": None,
        "recent_excerpt": None,
        "search_hits": [],
        "plan_events": [],
        "agent_events": [],
        "worktree_paths_mentioned": [],
        "parse_errors": 0,
    }
    mentioned: set[str] = set()
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                if deadline is not None and time.monotonic() >= deadline:
                    record["deadline_truncated"] = True
                    break
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
                for match in mentioned_worktree_paths(line):
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
    path: Path,
    *args: str,
    check: bool = False,
    deadline: float | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(path), *args]
    timeout = 20
    if deadline is not None:
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            return subprocess.CompletedProcess(
                command, 124, "", "overall collection deadline exceeded"
            )
        timeout = min(timeout, max(1, remaining))
    try:
        return subprocess.run(
            command,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        if check:
            raise
        return subprocess.CompletedProcess(command, 124, "", str(error))


def discover_git_roots(
    workspace: Path,
    session_cwds: Iterable[str | None],
    deadline: float | None = None,
) -> tuple[list[Path], list[str]]:
    candidates: set[Path] = set()
    errors: list[str] = []
    if workspace.is_dir():
        for current, dirs, files in os.walk(workspace):
            if deadline is not None and time.monotonic() >= deadline:
                errors.append("Git repository discovery stopped at overall deadline")
                dirs[:] = []
                break
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
        result = run_git(candidate, "rev-parse", "--show-toplevel", deadline=deadline)
        if result.returncode == 0:
            candidates.add(Path(result.stdout.strip()))
    common_roots: dict[str, Path] = {}
    for candidate in sorted(candidates):
        result = run_git(
            candidate,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
            deadline=deadline,
        )
        if result.returncode != 0:
            errors.append(f"{candidate}: {redact(result.stderr)}")
            continue
        common_roots.setdefault(result.stdout.strip(), candidate)
    return sorted(common_roots.values()), errors


def default_base(path: Path, deadline: float | None = None) -> str | None:
    symbolic = run_git(
        path,
        "symbolic-ref",
        "--quiet",
        "--short",
        "refs/remotes/origin/HEAD",
        deadline=deadline,
    )
    if symbolic.returncode == 0:
        return symbolic.stdout.strip()
    for candidate in ("origin/main", "origin/master", "main", "master"):
        if (
            run_git(
                path,
                "rev-parse",
                "--verify",
                "--quiet",
                candidate,
                deadline=deadline,
            ).returncode
            == 0
        ):
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
    path: Path,
    branch: str | None,
    base: str | None,
    deadline: float | None = None,
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
            "inspection_errors": ["worktree path does not exist; it may be prunable"],
        }
    status = run_git(path, "status", "--porcelain=v2", "--branch", deadline=deadline)
    dirty = run_git(path, "status", "--porcelain", deadline=deadline)
    recent = run_git(
        path,
        "log",
        "-5",
        "--date=iso-strict",
        "--pretty=format:%H%x09%ad%x09%s",
        deadline=deadline,
    )
    upstream = run_git(
        path,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        deadline=deadline,
    )
    head = run_git(path, "rev-parse", "HEAD", deadline=deadline)
    inspection_errors = [
        f"{name}: {redact(result.stderr or 'command failed')}"
        for name, result in (
            ("status", status),
            ("dirty status", dirty),
            ("recent log", recent),
            ("HEAD", head),
        )
        if result.returncode != 0
    ]
    row: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "branch": branch,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "base": base,
        "merge_basis": "local_ref_snapshot",
        "upstream": upstream.stdout.strip() if upstream.returncode == 0 else None,
        "status_headers": [
            line for line in status.stdout.splitlines() if line.startswith("# ")
        ],
        "dirty_files": [redact(line, 500) for line in dirty.stdout.splitlines()[:100]],
        "recent_commits": [redact(line, 1000) for line in recent.stdout.splitlines()],
        "unique_commits_vs_base": None,
        "changed_files_vs_base": [],
        "merged_into_base": None,
        "inspection_errors": inspection_errors,
    }
    if base and head.returncode == 0:
        count = run_git(path, "rev-list", "--count", f"{base}..HEAD", deadline=deadline)
        if count.returncode == 0:
            row["unique_commits_vs_base"] = int(count.stdout.strip())
        else:
            row["inspection_errors"].append(
                f"base commit count: {redact(count.stderr or 'command failed')}"
            )
        changed = run_git(
            path, "diff", "--name-only", f"{base}...HEAD", deadline=deadline
        )
        if changed.returncode == 0:
            row["changed_files_vs_base"] = changed.stdout.splitlines()[:200]
        else:
            row["inspection_errors"].append(
                f"base changed files: {redact(changed.stderr or 'command failed')}"
            )
        merged = run_git(
            path, "merge-base", "--is-ancestor", "HEAD", base, deadline=deadline
        )
        if merged.returncode in {0, 1}:
            row["merged_into_base"] = merged.returncode == 0
        else:
            row["inspection_errors"].append(
                f"base ancestry: {redact(merged.stderr or 'command failed')}"
            )
    return row


def inspect_repositories(
    roots: list[Path], deadline: float | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    def inspect_repository(
        root: Path,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if deadline is not None and time.monotonic() >= deadline:
            return None, f"{root}: skipped because overall collection deadline expired"
        base = default_base(root, deadline)
        worktrees = run_git(root, "worktree", "list", "--porcelain", deadline=deadline)
        if worktrees.returncode != 0:
            return None, f"{root}: {redact(worktrees.stderr)}"
        inspected: list[dict[str, Any]] = []
        for entry in parse_worktree_porcelain(worktrees.stdout):
            worktree_path = Path(entry["worktree"])
            branch = entry.get("branch", "").removeprefix("refs/heads/") or None
            inspected.append(inspect_worktree(worktree_path, branch, base, deadline))
        remote = run_git(root, "remote", "get-url", "origin", deadline=deadline)
        base_head = (
            run_git(root, "rev-parse", base, deadline=deadline) if base else None
        )
        checked_out = {
            row["branch"] for row in inspected if isinstance(row.get("branch"), str)
        }
        branches = run_git(
            root,
            "for-each-ref",
            "--format=%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)",
            "refs/heads",
            deadline=deadline,
        )
        branches_without_worktrees = []
        if branches.returncode == 0:
            for line in branches.stdout.splitlines():
                branch, head, upstream, tracking = (line.split("\t") + ["", "", ""])[:4]
                if branch in checked_out or branch in PRIMARY_BRANCHES:
                    continue
                branches_without_worktrees.append(
                    {
                        "branch": branch,
                        "head": head,
                        "upstream": upstream or None,
                        "tracking": tracking or None,
                    }
                )
        repository_errors = [
            f"{row['path']}: {'; '.join(row['inspection_errors'])}"
            for row in inspected
            if row.get("inspection_errors")
        ]
        if base_head is not None and base_head.returncode != 0:
            repository_errors.append(
                f"{root}: base snapshot: {redact(base_head.stderr or 'command failed')}"
            )
        if branches.returncode != 0:
            repository_errors.append(
                f"{root}: branch inventory: "
                f"{redact(branches.stderr or 'command failed')}"
            )
        return (
            {
                "root": str(root),
                "origin": (
                    sanitize_origin(remote.stdout.strip())
                    if remote.returncode == 0
                    else None
                ),
                "default_base": base,
                "base_snapshot": {
                    "ref": base,
                    "head": (
                        base_head.stdout.strip()
                        if base_head is not None and base_head.returncode == 0
                        else None
                    ),
                    "freshness": "local_ref_only_no_fetch",
                },
                "worktrees": inspected,
                "local_branches_without_worktrees": branches_without_worktrees,
            },
            " | ".join(repository_errors) if repository_errors else None,
        )

    repositories: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(roots)))) as executor:
        for repository, error in executor.map(inspect_repository, roots):
            if repository is not None:
                repositories.append(repository)
            if error:
                errors.append(error)
    repositories.sort(key=lambda row: row["root"])
    errors.sort()
    return repositories, errors


def correlate(
    sessions: list[dict[str, Any]], repositories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    worktrees = [row for repo in repositories for row in repo["worktrees"]]
    lanes: list[dict[str, Any]] = []

    for session in sessions:
        cwd = session.get("cwd")
        primary: dict[str, Any] | None = None
        if cwd:
            cwd_path = Path(cwd)
            cwd_matches = [
                row
                for row in worktrees
                if cwd_path == Path(row["path"])
                or Path(row["path"]) in cwd_path.parents
            ]
            if cwd_matches:
                primary = max(cwd_matches, key=lambda row: len(row["path"]))
        mentioned_dependencies: list[dict[str, Any]] = []
        for mentioned in session.get("worktree_paths_mentioned", []):
            mentioned_path = Path(mentioned)
            path_matches = [
                row
                for row in worktrees
                if mentioned_path == Path(row["path"])
                or Path(row["path"]) in mentioned_path.parents
            ]
            if path_matches:
                dependency = max(path_matches, key=lambda row: len(row["path"]))
                if primary is None or dependency["path"] != primary["path"]:
                    mentioned_dependencies.append(
                        {
                            "path": dependency["path"],
                            "relationship": "mentioned_not_owned",
                        }
                    )
        lanes.append(
            {
                "lane_id": f"session:{session['tool']}:{session['session_id']}",
                "kind": "session_candidate",
                "worktree": primary,
                "session_refs": [
                    {
                        "tool": session["tool"],
                        "session_id": session["session_id"],
                        "path": session["path"],
                        "modified_at": session["modified_at"],
                        "match_reason": "cwd" if primary else "unmapped_session",
                    }
                ],
                "mentioned_worktree_dependencies": sorted(
                    mentioned_dependencies, key=lambda row: row["path"]
                ),
                "task_boundaries_unresolved": True,
                "signals": [],
            }
        )
    for worktree in worktrees:
        lanes.append(
            {
                "lane_id": f"worktree:{worktree['path']}",
                "kind": "worktree_snapshot",
                "worktree": worktree,
                "session_refs": [],
                "mentioned_worktree_dependencies": [],
                "task_boundaries_unresolved": False,
                "signals": [],
            }
        )
    for lane in lanes:
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
        if lane["kind"] == "session_candidate":
            if lane["worktree"] is None:
                lane["signals"].append("unmapped_session")
            if lane["mentioned_worktree_dependencies"]:
                lane["signals"].append("mentioned_worktree_dependency")
            session_id = lane["session_refs"][0]["session_id"]
            matching_session = next(
                (
                    session
                    for session in sessions
                    if session.get("session_id") == session_id
                    and session.get("tool") == lane["session_refs"][0]["tool"]
                ),
                None,
            )
            if matching_session and matching_session.get("inventory_only"):
                lane["signals"].append("inventory_only_unverified")
            if matching_session and matching_session.get("activity_block_only"):
                lane["signals"].append("activity_block_only_unverified")
        lane["session_refs"].sort(
            key=lambda row: row["modified_at"] or "", reverse=True
        )
    return sorted(
        lanes,
        key=lambda row: (
            (row["session_refs"][0]["modified_at"] or "") if row["session_refs"] else ""
        ),
        reverse=True,
    )


def transcript_paths(
    home: Path,
    cutoff: float,
    limit: int,
    deadline: float | None = None,
) -> tuple[list[tuple[Path, str]], dict[str, Any]]:
    found_by_tool: dict[str, list[tuple[Path, float]]] = {
        "claude": [],
        "codex": [],
    }
    deadline_truncated_by_tool: dict[str, bool] = {
        "claude": False,
        "codex": False,
    }
    claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude"))
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    roots = (
        (claude_home / "projects", "claude"),
        (codex_home / "sessions", "codex"),
    )
    for root, tool in roots:
        if deadline is not None and time.monotonic() >= deadline:
            deadline_truncated_by_tool[tool] = True
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            if deadline is not None and time.monotonic() >= deadline:
                deadline_truncated_by_tool[tool] = True
                break
            try:
                modified = path.stat().st_mtime
                if modified >= cutoff:
                    found_by_tool[tool].append((path, modified))
            except OSError:
                continue
    selected: list[tuple[Path, str]] = []
    per_tool: dict[str, Any] = {}
    for tool, paths in found_by_tool.items():
        paths.sort(key=lambda item: item[1], reverse=True)
        chosen = paths[:limit]
        selected.extend((path, tool) for path, _ in chosen)
        per_tool[tool] = {
            "discovered": len(paths),
            "selected": len(chosen),
            "omitted": max(0, len(paths) - len(chosen)),
            "limit_truncated": len(paths) > limit,
            "deadline_truncated": deadline_truncated_by_tool[tool],
            "truncated": (len(paths) > limit or deadline_truncated_by_tool[tool]),
        }
    selected_mtimes = {
        path: modified for paths in found_by_tool.values() for path, modified in paths
    }
    selected.sort(key=lambda item: selected_mtimes[item[0]], reverse=True)
    return selected, {
        "limit_per_tool": limit,
        "per_tool": per_tool,
        "discovered": sum(row["discovered"] for row in per_tool.values()),
        "selected": len(selected),
        "omitted": sum(row["omitted"] for row in per_tool.values()),
        "truncated": any(row["truncated"] for row in per_tool.values()),
        "deadline_truncated": any(
            row["deadline_truncated"] for row in per_tool.values()
        ),
    }


def build_recent_session_index(
    selected_paths: list[tuple[Path, str]],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path, tool in selected_paths:
        try:
            modified_at = iso_from_epoch(path.stat().st_mtime)
        except OSError:
            continue
        aliases = {path.stem}
        match = UUID_SUFFIX.search(path.stem)
        if match:
            aliases.add(match.group(1))
        row = {
            "path": str(path),
            "tool": tool,
            "modified_at": modified_at,
        }
        for alias in aliases:
            index.setdefault(alias, row)
    return index


def limit_transcript_selection(
    selected_paths: list[tuple[Path, str]],
    discovery_coverage: dict[str, Any],
    limit: int,
) -> tuple[list[tuple[Path, str]], dict[str, Any]]:
    """Reuse a broader recent-session scan for a smaller raw fallback window."""
    selected_by_tool: dict[str, int] = {"claude": 0, "codex": 0}
    limited: list[tuple[Path, str]] = []
    for path, tool in selected_paths:
        if selected_by_tool.setdefault(tool, 0) >= limit:
            continue
        selected_by_tool[tool] += 1
        limited.append((path, tool))
    per_tool: dict[str, Any] = {}
    source_per_tool = discovery_coverage.get("per_tool", {})
    for tool in ("claude", "codex"):
        discovered = int(source_per_tool.get(tool, {}).get("discovered", 0))
        selected = selected_by_tool.get(tool, 0)
        per_tool[tool] = {
            "discovered": discovered,
            "selected": selected,
            "omitted": max(0, discovered - selected),
            "limit_truncated": discovered > selected,
            "deadline_truncated": bool(
                source_per_tool.get(tool, {}).get("deadline_truncated")
            ),
            "truncated": (
                discovered > selected
                or bool(source_per_tool.get(tool, {}).get("deadline_truncated"))
            ),
        }
    return limited, {
        "limit_per_tool": limit,
        "per_tool": per_tool,
        "discovered": sum(row["discovered"] for row in per_tool.values()),
        "selected": len(limited),
        "omitted": sum(row["omitted"] for row in per_tool.values()),
        "truncated": any(row["truncated"] for row in per_tool.values()),
        "deadline_truncated": any(
            row["deadline_truncated"] for row in per_tool.values()
        ),
        "reused_recent_session_index": True,
    }


def run_cortex_json(
    cortex_binary: str,
    *args: str,
    timeout: int = 30,
    deadline: float | None = None,
) -> tuple[Any | None, str | None]:
    command = [cortex_binary, "sessions", *args, "--json"]
    if deadline is not None:
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            return (
                None,
                f"{' '.join(command[:3])}: overall collection deadline exceeded",
            )
        timeout = min(timeout, max(1, remaining))
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"{' '.join(command[:3])}: {redact(str(error))}"
    if completed.returncode != 0:
        return None, (
            f"{' '.join(command[:3])}: exit {completed.returncode}: "
            f"{redact(completed.stderr or completed.stdout)}"
        )
    try:
        return json.loads(completed.stdout), None
    except json.JSONDecodeError as error:
        return None, f"{' '.join(command[:3])}: invalid JSON: {error}"


def parse_cortex_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def project_in_workspace(project: Any, workspace: Path) -> bool:
    if not isinstance(project, str):
        return False
    try:
        Path(project).resolve(strict=False).relative_to(workspace)
        return True
    except (OSError, ValueError):
        return False


def cortex_session_record(
    project: str,
    tool: str | None,
    session_id: str,
    first_seen: str | None,
    last_seen: str | None,
) -> dict[str, Any]:
    modified = last_seen or first_seen or ""
    return {
        "tool": tool or "unknown",
        "path": f"cortex://session/{session_id}",
        "session_id": session_id,
        "cwd": project,
        "started_at": first_seen,
        "last_event_at": last_seen,
        "modified_at": modified,
        "git": {},
        "last_user_excerpt": None,
        "last_assistant_excerpt": None,
        "recent_excerpt": None,
        "search_hits": [],
        "plan_events": [],
        "agent_events": [],
        "worktree_paths_mentioned": [],
        "parse_errors": 0,
        "evidence_source": "cortex",
        "cortex_queries": [],
        "inventory_only": False,
        "search_only": False,
    }


def cortex_shape_error(command: str, result: Any) -> str | None:
    if command == "watchstatus":
        if not isinstance(result, dict) or not isinstance(result.get("health"), dict):
            return "watchstatus response must contain an object health field"
    elif command == "projects":
        if not isinstance(result, dict) or not isinstance(result.get("projects"), list):
            return "projects response must contain a projects list"
        for row in result["projects"]:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("project"), str)
                or not isinstance(row.get("tools"), list)
                or not all(isinstance(tool, str) for tool in row["tools"])
                or not isinstance(row.get("session_count"), int)
                or not isinstance(row.get("event_count"), int)
                or not isinstance(row.get("first_seen"), str)
                or not isinstance(row.get("last_seen"), str)
            ):
                return "every projects row must match the documented field types"
    elif command == "blocks":
        if not isinstance(result, dict) or not isinstance(result.get("blocks"), list):
            return "blocks response must contain a blocks list"
        for row in result["blocks"]:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("project"), str)
                or not isinstance(row.get("tool"), str)
                or not isinstance(row.get("session_count"), int)
                or not isinstance(row.get("event_count"), int)
                or not isinstance(row.get("bucket_start"), str)
                or not isinstance(row.get("bucket_end"), str)
            ):
                return "every blocks row must match the documented field types"
    elif command == "session_errors":
        if not isinstance(result, list):
            return "errors response must be a list"
        for row in result:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("canonical_path"), str)
                or not isinstance(row.get("source_kind"), str)
                or not isinstance(row.get("line_no"), int)
                or not isinstance(row.get("error"), str)
                or not isinstance(row.get("seen_at"), str)
            ):
                return "every errors row must match the documented field types"
    elif command.startswith("search:"):
        if not isinstance(result, dict) or not isinstance(result.get("sessions"), list):
            return "search response must contain a sessions list"
        for row in result["sessions"]:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("project"), str)
                or not isinstance(row.get("tool"), str)
                or not isinstance(row.get("session_id"), str)
                or not isinstance(row.get("first_seen"), str)
                or not isinstance(row.get("last_seen"), str)
            ):
                return "every search session row must match the documented field types"
    elif command.startswith("context:"):
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("sessions"), list)
            or not isinstance(result.get("recent_entries"), list)
        ):
            return "context response must contain sessions and recent_entries lists"
        if not all(isinstance(session_id, str) for session_id in result["sessions"]):
            return "every context session ID must be a string"
        if not all(isinstance(entry, dict) for entry in result["recent_entries"]):
            return "every context recent entry must be an object"
        for entry in result["recent_entries"]:
            if (
                not isinstance(entry.get("timestamp") or entry.get("received_at"), str)
                or not isinstance(entry.get("ai_session_id"), str)
                or not isinstance(entry.get("ai_tool"), str)
                or not isinstance(entry.get("ai_transcript_path"), str)
                or not isinstance(entry.get("message"), str)
            ):
                return "every context recent entry must match transcript field types"
    return None


def collect_cortex_evidence(
    workspace: Path,
    since_hours: float,
    project_limit: int,
    context_limit: int,
    recent_session_index: dict[str, dict[str, Any]],
    session_index_coverage: dict[str, Any],
    cortex_binary: str,
    cutoff: dt.datetime,
    deadline: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], bool]:
    errors: list[str] = []
    failed_calls: list[str] = []
    since = f"{since_hours:g}h"

    base_calls = {
        "watchstatus": ("watchstatus",),
        "projects": ("projects", "--since", since),
        "blocks": (
            "blocks",
            "--since",
            since,
            "--limit",
            "200",
            "--detail",
            "compact",
        ),
        "session_errors": ("errors", "--limit", "25"),
    }
    base_results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(base_calls)) as executor:
        futures = {
            label: executor.submit(
                run_cortex_json,
                cortex_binary,
                *arguments,
                deadline=deadline,
            )
            for label, arguments in base_calls.items()
        }
        for label, future in futures.items():
            result, error = future.result()
            base_results[label] = result
            shape_error = cortex_shape_error(label, result) if not error else None
            if shape_error:
                error = f"cortex sessions {label}: invalid response: {shape_error}"
            if error:
                errors.append(error)
                failed_calls.append(label)
    watchstatus = base_results["watchstatus"]
    projects = base_results["projects"]
    blocks = base_results["blocks"]
    session_errors = base_results["session_errors"]
    block_rows = blocks.get("blocks", []) if isinstance(blocks, dict) else []

    search_results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(CORTEX_SEARCH_QUERIES)) as executor:
        futures = {
            label: executor.submit(
                run_cortex_json,
                cortex_binary,
                "search",
                query,
                "--since",
                since,
                "--limit",
                "100",
                timeout=60,
                deadline=deadline,
            )
            for label, query in CORTEX_SEARCH_QUERIES.items()
        }
        for label, future in futures.items():
            result, error = future.result()
            search_results[label] = result
            shape_error = (
                cortex_shape_error(f"search:{label}", result) if not error else None
            )
            if shape_error:
                error = f"cortex sessions search: invalid response: {shape_error}"
            if error:
                errors.append(error)
                failed_calls.append(f"search:{label}")

    health = watchstatus.get("health", {}) if isinstance(watchstatus, dict) else {}
    stale_reasons: list[str] = []
    if not isinstance(watchstatus, dict) or not isinstance(health, dict):
        stale_reasons.append("Cortex watchstatus health is unavailable")
    if health.get("schema_current") is not True:
        stale_reasons.append("Cortex transcript schema is not confirmed current")
    for indicator in health.get("stale_indicators") or []:
        stale_reasons.append(
            f"Cortex watcher reports stale index: {redact(str(indicator))}"
        )
    last_ingest = parse_cortex_time(health.get("last_successful_ingest_at"))
    if last_ingest is None:
        stale_reasons.append("Cortex last successful ingest time is unavailable")
    elif last_ingest < cutoff:
        stale_reasons.append(
            "Cortex has no successful transcript ingest in the evidence window"
        )

    project_rows = projects.get("projects", []) if isinstance(projects, dict) else []
    candidates = [
        row
        for row in project_rows
        if isinstance(row, dict) and project_in_workspace(row.get("project"), workspace)
    ]
    candidates.sort(key=lambda row: row.get("last_seen") or "", reverse=True)
    candidates = candidates[:project_limit]

    contexts: dict[str, Any] = {}
    failed_contexts: list[str] = []
    with ThreadPoolExecutor(max_workers=min(3, max(1, len(candidates)))) as executor:
        futures = {
            project_row["project"]: executor.submit(
                run_cortex_json,
                cortex_binary,
                "context",
                project_row["project"],
                "--limit",
                str(context_limit),
                timeout=60,
                deadline=deadline,
            )
            for project_row in candidates
        }
        for project, future in futures.items():
            context, error = future.result()
            shape_error = (
                cortex_shape_error(f"context:{project}", context) if not error else None
            )
            if shape_error:
                error = f"cortex sessions context: invalid response: {shape_error}"
            if error:
                errors.append(error)
                failed_contexts.append(project)
                failed_calls.append(f"context:{project}")
            elif context is not None:
                contexts[project] = context

    sessions_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    def ensure_session(
        project: str,
        tool: str | None,
        session_id: str,
        first_seen: str | None,
        last_seen: str | None,
    ) -> dict[str, Any]:
        key = (project, session_id)
        session = sessions_by_key.get(key)
        if session is None:
            session = cortex_session_record(
                project, tool, session_id, first_seen, last_seen
            )
            sessions_by_key[key] = session
        else:
            if session["tool"] == "unknown" and tool:
                session["tool"] = tool
            session["started_at"] = session["started_at"] or first_seen
            session["last_event_at"] = last_seen or session["last_event_at"]
            session["modified_at"] = last_seen or session["modified_at"]
        return session

    for label, result in search_results.items():
        rows = result.get("sessions", []) if isinstance(result, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            project = row.get("project")
            session_id = row.get("session_id")
            if (
                not project_in_workspace(project, workspace)
                or not isinstance(session_id, str)
                or not session_id
            ):
                continue
            existed = (project, session_id) in sessions_by_key
            session = ensure_session(
                project,
                row.get("tool"),
                session_id,
                row.get("first_seen"),
                row.get("last_seen"),
            )
            if not existed:
                session["search_only"] = True
            snippet = redact(str(row.get("best_snippet") or ""), 1200)
            session["cortex_queries"].append(label)
            session["search_hits"].append(
                {
                    "query": label,
                    "snippet": snippet,
                    "confidence": "lead_only",
                }
            )
            if label == "plans" and VERIFIED_PLAN_EVENT.fullmatch(snippet):
                session["search_only"] = False
                session["plan_events"].append(
                    {
                        "query": CORTEX_SEARCH_QUERIES[label],
                        "snippet": snippet,
                        "verified_typed_event": True,
                    }
                )
            elif label == "unfinished":
                session["recent_excerpt"] = snippet or session["recent_excerpt"]
            for match in mentioned_worktree_paths(snippet):
                session["worktree_paths_mentioned"].append(match)

    enumerated_context_session_ids: set[tuple[str, str]] = set()
    evidenced_session_ids: set[tuple[str, str]] = set(sessions_by_key)
    for project, context in contexts.items():
        context_session_ids = (
            context.get("sessions", []) if isinstance(context, dict) else []
        )
        for session_id in context_session_ids:
            if not isinstance(session_id, str) or not session_id:
                continue
            enumerated_context_session_ids.add((project, session_id))
        for session_id in context_session_ids:
            if not isinstance(session_id, str) or not session_id:
                continue
            if (project, session_id) in sessions_by_key:
                continue
            indexed = recent_session_index.get(session_id)
            if not indexed:
                continue
            inventory_session = ensure_session(
                project,
                indexed["tool"],
                session_id,
                indexed["modified_at"],
                indexed["modified_at"],
            )
            inventory_session["path"] = indexed["path"]
            inventory_session["inventory_only"] = True
            inventory_session["inventory_selection"] = (
                "recent_transcript_metadata_match"
            )
            evidenced_session_ids.add((project, session_id))
        entries = context.get("recent_entries", []) if isinstance(context, dict) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            timestamp = entry.get("timestamp") or entry.get("received_at")
            parsed_timestamp = parse_cortex_time(timestamp)
            if parsed_timestamp and parsed_timestamp < cutoff:
                continue
            session_id = entry.get("ai_session_id")
            if not isinstance(session_id, str) or not session_id:
                continue
            session = ensure_session(
                project,
                entry.get("ai_tool"),
                session_id,
                timestamp,
                timestamp,
            )
            evidenced_session_ids.add((project, session_id))
            session["inventory_only"] = False
            session["search_only"] = False
            transcript_path = entry.get("ai_transcript_path")
            if isinstance(transcript_path, str) and transcript_path:
                session["path"] = transcript_path
            message = redact(str(entry.get("message") or ""), 1200)
            if message and not message.startswith("[function_call"):
                session["recent_excerpt"] = message
            for match in mentioned_worktree_paths(message):
                session["worktree_paths_mentioned"].append(match)

    search_leads: list[dict[str, Any]] = []
    for key, session in list(sessions_by_key.items()):
        session["cortex_queries"] = sorted(set(session["cortex_queries"]))
        session["worktree_paths_mentioned"] = sorted(
            set(session["worktree_paths_mentioned"])
        )
        session["plan_events"] = session["plan_events"][-5:]
        session["search_hits"] = session["search_hits"][-10:]
        if session.get("search_only"):
            search_leads.append(
                {
                    "project": session["cwd"],
                    "tool": session["tool"],
                    "session_id": session["session_id"],
                    "first_seen": session["started_at"],
                    "last_seen": session["last_event_at"],
                    "hits": session["search_hits"],
                    "classification": "lead_only_not_a_lane",
                }
            )
            del sessions_by_key[key]

    for block in block_rows:
        if not isinstance(block, dict):
            continue
        project = block.get("project")
        tool = block.get("tool")
        if not project_in_workspace(project, workspace):
            continue
        if any(
            session.get("cwd") == project and session.get("tool") == tool
            for session in sessions_by_key.values()
        ):
            continue
        bucket = str(block.get("bucket_start") or "unknown").replace(" ", "T")
        session_id = f"activity-block:{tool or 'unknown'}:{bucket}"
        activity = cortex_session_record(
            project,
            tool,
            session_id,
            block.get("bucket_start"),
            block.get("bucket_end"),
        )
        activity["evidence_source"] = "cortex_activity_block"
        activity["activity_block_only"] = True
        activity["recent_excerpt"] = (
            f"Cortex activity block: {block.get('session_count')} session(s), "
            f"{block.get('event_count')} event(s)"
        )
        sessions_by_key[(project, session_id)] = activity

    usable = isinstance(projects, dict) and not stale_reasons and not failed_calls
    health_summary = {
        key: health.get(key)
        for key in (
            "db_schema_version",
            "known_schema_version",
            "schema_current",
            "last_successful_ingest_at",
            "recent_failure_count",
            "stale_indicators",
        )
    }
    project_summaries = [
        {
            key: row.get(key)
            for key in (
                "project",
                "tools",
                "event_count",
                "session_count",
                "first_seen",
                "last_seen",
            )
        }
        for row in project_rows
        if isinstance(row, dict)
    ]
    block_summaries = [
        {
            key: row.get(key)
            for key in (
                "bucket_start",
                "bucket_end",
                "project",
                "tool",
                "session_count",
                "event_count",
            )
        }
        for row in block_rows
        if isinstance(row, dict)
    ]
    search_summaries = {
        label: {
            "query": CORTEX_SEARCH_QUERIES[label],
            "returned_sessions": len(
                result.get("sessions", []) if isinstance(result, dict) else []
            ),
            "total_candidates": (
                result.get("total_candidates") if isinstance(result, dict) else None
            ),
            "truncated": result.get("truncated") if isinstance(result, dict) else None,
            "candidate_window_truncated": (
                result.get("candidate_window_truncated")
                if isinstance(result, dict)
                else None
            ),
        }
        for label, result in search_results.items()
    }
    context_summaries = {
        project: {
            "time_bounded_session_ids": [
                session_id
                for session_id in context.get("sessions", [])
                if isinstance(session_id, str) and session_id in recent_session_index
            ],
            "session_count": len(context.get("sessions", [])),
            "recent_entries_returned": len(context.get("recent_entries", [])),
            "recent_entries_truncated": bool(
                context.get("recent_entries_truncated", False)
            ),
            "first_seen": context.get("first_seen"),
            "last_seen": context.get("last_seen"),
        }
        for project, context in contexts.items()
        if isinstance(context, dict)
    }
    indexed_error_summaries = [
        {
            "canonical_path": redact(str(row.get("canonical_path") or ""), 1200),
            "source_kind": row.get("source_kind"),
            "line_no": row.get("line_no"),
            "error": redact(str(row.get("error") or ""), 500),
            "seen_at": row.get("seen_at"),
        }
        for row in (session_errors if isinstance(session_errors, list) else [])
        if isinstance(row, dict)
    ]
    cortex = {
        "usable": usable,
        "status": "healthy" if usable else "degraded",
        "stale_reasons": stale_reasons,
        "failed_calls": failed_calls,
        "failed_contexts": failed_contexts,
        "watchstatus": {
            "service": (
                watchstatus.get("service") if isinstance(watchstatus, dict) else None
            ),
            "active": (
                watchstatus.get("active") if isinstance(watchstatus, dict) else None
            ),
            "health": health_summary,
        },
        "projects": {
            "discovered": len(project_summaries),
            "truncated": (
                bool(projects.get("truncated", False))
                if isinstance(projects, dict)
                else None
            ),
            "items": project_summaries,
        },
        "blocks": {
            "returned": len(block_summaries),
            "truncated": (
                bool(blocks.get("truncated", False))
                if isinstance(blocks, dict)
                else None
            ),
            "items": block_summaries,
        },
        "session_errors": indexed_error_summaries,
        "searches": search_summaries,
        "search_leads": search_leads,
        "contexts": context_summaries,
        "coverage": {
            "candidate_projects": len(candidates),
            "projects_with_context": len(contexts),
            "projects_without_context": failed_contexts,
            "context_selection_truncated": len(
                [
                    row
                    for row in project_rows
                    if isinstance(row, dict)
                    and project_in_workspace(row.get("project"), workspace)
                ]
            )
            > project_limit,
            "contexts_with_truncated_recent_entries": sorted(
                project
                for project, summary in context_summaries.items()
                if summary["recent_entries_truncated"]
            ),
            "enumerated_session_ids": len(enumerated_context_session_ids),
            "time_bounded_session_ids": len(evidenced_session_ids),
            "session_ids_without_time_bounded_evidence": len(
                enumerated_context_session_ids - evidenced_session_ids
            ),
            "inventory_only_session_ids_materialized": len(
                [
                    session
                    for session in sessions_by_key.values()
                    if session.get("inventory_only")
                ]
            ),
            "inventory_only_session_ids_omitted": max(
                0,
                len(enumerated_context_session_ids - evidenced_session_ids)
                - len(
                    [
                        session
                        for session in sessions_by_key.values()
                        if session.get("inventory_only")
                    ]
                ),
            ),
            "recent_session_index": session_index_coverage,
        },
        "project_limit": project_limit,
        "context_limit": context_limit,
    }
    errors.extend(stale_reasons)
    sessions = sorted(
        sessions_by_key.values(),
        key=lambda row: row["modified_at"] or "",
        reverse=True,
    )
    return sessions, cortex, errors, usable


def merge_session_evidence(
    cortex_sessions: list[dict[str, Any]],
    raw_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for session in cortex_sessions + raw_sessions:
        key = (
            str(session.get("tool") or "unknown"),
            str(session.get("session_id") or ""),
            str(session.get("cwd") or ""),
        )
        previous = merged.get(key)
        if previous is None:
            merged[key] = session
            continue
        if session.get("evidence_source") != "cortex":
            for field in (
                "path",
                "started_at",
                "last_event_at",
                "modified_at",
                "last_user_excerpt",
                "last_assistant_excerpt",
                "plan_events",
                "agent_events",
                "worktree_paths_mentioned",
            ):
                if session.get(field):
                    previous[field] = session[field]
            previous["evidence_source"] = "cortex+raw_file"
    return sorted(
        merged.values(), key=lambda row: row.get("modified_at") or "", reverse=True
    )


def collect(
    workspace: Path,
    since_hours: float,
    transcript_limit: int,
    home: Path,
    source: str = "auto",
    cortex_binary: str = "cortex",
    cortex_project_limit: int = 12,
    cortex_context_limit: int = 50,
    session_index_limit: int = 500,
    repository_limit: int = 200,
    overall_timeout: int = 180,
    progress: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + overall_timeout
    now = dt.datetime.now(tz=dt.timezone.utc)
    cutoff_epoch = now.timestamp() - since_hours * 3600
    cutoff = dt.datetime.fromtimestamp(cutoff_epoch, tz=dt.timezone.utc)
    cortex: dict[str, Any] | None = None
    cortex_errors: list[str] = []
    cortex_usable = False
    sessions: list[dict[str, Any]] = []
    raw_coverage: dict[str, Any] | None = None
    index_paths: list[tuple[Path, str]] = []
    session_index_coverage: dict[str, Any] = {
        "limit_per_tool": session_index_limit,
        "per_tool": {},
        "discovered": 0,
        "selected": 0,
        "omitted": 0,
        "truncated": False,
        "deadline_truncated": False,
        "not_collected": True,
    }
    recent_session_index: dict[str, dict[str, Any]] = {}
    if source in {"auto", "cortex"}:
        index_paths, session_index_coverage = transcript_paths(
            home, cutoff_epoch, session_index_limit, deadline
        )
        recent_session_index = build_recent_session_index(index_paths)

    def progress_message(message: str) -> None:
        if progress:
            print(f"[resume-work-lanes] {message}", file=sys.stderr, flush=True)

    if source in {"auto", "cortex"}:
        progress_message("querying Cortex session intelligence")
        sessions, cortex, cortex_errors, cortex_usable = collect_cortex_evidence(
            workspace,
            since_hours,
            cortex_project_limit,
            cortex_context_limit,
            recent_session_index,
            session_index_coverage,
            cortex_binary,
            cutoff,
            deadline,
        )

    if source == "files" or (source == "auto" and not cortex_usable):
        progress_message("collecting bounded raw transcript fallback")
        if source == "auto":
            selected_paths, raw_coverage = limit_transcript_selection(
                index_paths, session_index_coverage, transcript_limit
            )
        else:
            selected_paths, raw_coverage = transcript_paths(
                home, cutoff_epoch, transcript_limit, deadline
            )
        raw_sessions = [
            parse_json_lines(path, tool, deadline)
            for path, tool in selected_paths
            if time.monotonic() < deadline
        ]
        if source == "auto" and sessions:
            sessions = merge_session_evidence(sessions, raw_sessions)
            source_used = "cortex_degraded_with_raw_fallback"
        else:
            sessions = raw_sessions
            source_used = "raw_files_fallback" if source == "auto" else "raw_files"
    elif cortex_usable:
        source_used = "cortex"
    elif source == "git-only":
        source_used = "git_only"
    else:
        source_used = "cortex_unavailable"

    progress_message("inspecting local Git repositories and worktrees")
    roots, discovery_errors = discover_git_roots(
        workspace, (session.get("cwd") for session in sessions), deadline
    )
    discovered_repositories = len(roots)
    roots = roots[:repository_limit]
    repositories, git_errors = inspect_repositories(roots, deadline)
    elapsed = time.monotonic() - started
    session_limitations: list[str] = []
    git_limitations: list[str] = []
    session_read_errors = [
        f"{session.get('path') or '<unknown transcript>'}: "
        f"{redact(str(session['read_error']))}"
        for session in sessions
        if session.get("read_error")
    ]
    if source_used == "git_only":
        session_status = "external_required"
        session_limitations.append("session evidence must be supplied by Cortex MCP")
    elif source_used == "cortex_unavailable":
        session_status = "unavailable"
        session_limitations.append("explicit Cortex source was unavailable")
    else:
        if cortex:
            if cortex["status"] != "healthy":
                session_limitations.append("Cortex was degraded")
            if cortex["projects"]["truncated"]:
                session_limitations.append("Cortex project inventory was truncated")
            if cortex["blocks"]["truncated"]:
                session_limitations.append("Cortex activity blocks were truncated")
            if cortex["coverage"]["context_selection_truncated"]:
                session_limitations.append("not every recent project received context")
            if cortex["coverage"]["contexts_with_truncated_recent_entries"]:
                session_limitations.append(
                    "one or more project contexts were truncated"
                )
            if cortex["coverage"]["session_ids_without_time_bounded_evidence"]:
                session_limitations.append(
                    "some context session IDs lack time-bounded evidence"
                )
            if cortex["coverage"]["recent_session_index"].get("deadline_truncated"):
                session_limitations.append(
                    "recent-session index discovery hit the deadline"
                )
            if any(
                summary.get("truncated") or summary.get("candidate_window_truncated")
                for summary in cortex["searches"].values()
            ):
                session_limitations.append("one or more Cortex searches were truncated")
        if raw_coverage and raw_coverage["truncated"]:
            session_limitations.append("raw transcript fallback was truncated")
        if raw_coverage and raw_coverage.get("deadline_truncated"):
            session_limitations.append("raw transcript discovery hit the deadline")
        if any(session.get("deadline_truncated") for session in sessions):
            session_limitations.append("raw transcript parsing hit the deadline")
        if session_read_errors:
            session_limitations.append(
                "one or more transcript files disappeared or could not be read"
            )
        session_status = "complete" if not session_limitations else "incomplete"

    if discovered_repositories > repository_limit:
        git_limitations.append("repository inventory exceeded its limit")
    if discovery_errors:
        git_limitations.append("one or more repositories could not be discovered")
    if git_errors:
        git_limitations.append("one or more repositories could not be inspected")
    if len(repositories) < len(roots):
        git_limitations.append("not every selected repository was inspected")
    if time.monotonic() > deadline:
        git_limitations.append("overall collection deadline was exceeded")
    git_status = "complete" if not git_limitations else "incomplete"
    return {
        "schema_version": 2,
        "collected_at": now.isoformat(),
        "cutoff": iso_from_epoch(cutoff_epoch),
        "workspace": str(workspace),
        "source_requested": source,
        "source_used": source_used,
        "cortex": cortex,
        "raw_fallback": raw_coverage,
        "sessions": sessions,
        "repositories": repositories,
        "correlated_lanes": correlate(sessions, repositories),
        "coverage": {
            "complete": session_status == "complete" and git_status == "complete",
            "session_inventory_status": session_status,
            "session_limitations": session_limitations,
            "git_inventory_status": git_status,
            "git_limitations": git_limitations,
            "repository_limit": repository_limit,
            "repositories_discovered": discovered_repositories,
            "repositories_inspected": len(repositories),
            "repositories_truncated": discovered_repositories > repository_limit,
            "local_ref_freshness": "local_ref_only_no_fetch",
            "overall_timeout_seconds": overall_timeout,
            "deadline_exceeded": time.monotonic() > deadline,
            "elapsed_seconds": round(elapsed, 3),
        },
        "errors": cortex_errors + session_read_errors + discovery_errors + git_errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "workspace")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--since-hours", type=float, default=72)
    parser.add_argument("--transcript-limit", type=int, default=100)
    parser.add_argument(
        "--source",
        choices=("auto", "cortex", "files", "git-only"),
        default="auto",
    )
    parser.add_argument("--cortex-binary", default="cortex")
    parser.add_argument("--cortex-project-limit", type=int, default=12)
    parser.add_argument("--cortex-context-limit", type=int, default=50)
    parser.add_argument("--session-index-limit", type=int, default=500)
    parser.add_argument("--repository-limit", type=int, default=200)
    parser.add_argument("--overall-timeout", type=int, default=180)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def write_private_output(output: Path, rendered: str) -> None:
    output = output.expanduser()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"output parent does not exist: {output.parent}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        fchmod = getattr(os, "fchmod", None)
        if callable(fchmod):
            fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as error:
            raise FileExistsError(
                f"refusing to overwrite existing output: {output}"
            ) from error
        temporary.unlink()
        if os.name == "posix":
            output.chmod(0o600)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def main() -> int:
    args = parse_args()
    positive = (
        args.since_hours,
        args.transcript_limit,
        args.cortex_project_limit,
        args.cortex_context_limit,
        args.session_index_limit,
        args.repository_limit,
        args.overall_timeout,
    )
    if any(value <= 0 for value in positive):
        print("time windows and collection limits must be positive", file=sys.stderr)
        return 2
    if bool(args.output) == bool(args.stdout):
        print("choose exactly one of --output PATH or --stdout", file=sys.stderr)
        return 2
    artifact = collect(
        args.workspace.expanduser().resolve(),
        args.since_hours,
        args.transcript_limit,
        args.home.expanduser().resolve(),
        args.source,
        args.cortex_binary,
        args.cortex_project_limit,
        args.cortex_context_limit,
        args.session_index_limit,
        args.repository_limit,
        args.overall_timeout,
        args.progress,
    )
    rendered = json.dumps(artifact, indent=None if args.compact else 2, sort_keys=True)
    if args.output:
        try:
            write_private_output(args.output, rendered)
        except OSError as error:
            print(str(error), file=sys.stderr)
            return 2
        print(args.output.expanduser().resolve())
    else:
        print(rendered)
    if args.source == "cortex" and artifact["source_used"] != "cortex":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
