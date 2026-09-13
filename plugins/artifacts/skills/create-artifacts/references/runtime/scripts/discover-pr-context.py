#!/usr/bin/env python3
"""Discover evidence-bearing artifacts and AI transcripts for a GitHub PR."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ARTIFACT_DIRS = ("reports", "proposals", "plans", "specs", "research", "sessions", "docs")
SESSION_ROOTS = (Path.home() / ".codex" / "sessions", Path.home() / ".claude" / "projects")
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{3,}")


def run_json(argv: list[str], *, env: dict[str, str] | None = None) -> Any:
    result = subprocess.run(argv, check=True, text=True, capture_output=True, env=env)
    return json.loads(result.stdout)


def gh(path: str) -> Any:
    return run_json(["gh", "api", path])


def gh_pages(path: str) -> list[Any]:
    """Fetch every page from a GitHub REST collection endpoint."""
    items: list[Any] = []
    separator = "&" if "?" in path else "?"
    page = 1
    while True:
        batch = gh(f"{path}{separator}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise TypeError(f"expected a list from paginated GitHub endpoint: {path}")
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def pr_context(repository: str, number: int) -> dict[str, Any]:
    pr = gh(f"repos/{repository}/pulls/{number}")
    files = gh_pages(f"repos/{repository}/pulls/{number}/files")
    commits = gh_pages(f"repos/{repository}/pulls/{number}/commits")
    compare = gh(f"repos/{repository}/compare/{pr['base']['sha']}...{pr['head']['sha']}")
    return {
        "repository": repository,
        "number": number,
        "url": pr["html_url"],
        "title": pr["title"],
        "body": pr.get("body") or "",
        "state": pr["state"],
        "draft": pr["draft"],
        "created_at": pr["created_at"],
        "updated_at": pr["updated_at"],
        "base_branch": pr["base"]["ref"],
        "base_sha": pr["base"]["sha"],
        "head_branch": pr["head"]["ref"],
        "head_sha": pr["head"]["sha"],
        "merge_base": compare["merge_base_commit"]["sha"],
        "files": [item["filename"] for item in files],
        "commits": [{"sha": item["sha"], "message": item["commit"]["message"]} for item in commits],
    }


def add_signal(signals: list[dict[str, Any]], score: int, kind: str, value: str) -> int:
    signals.append({"kind": kind, "value": value, "score": score})
    return score


def match_artifacts(root: Path, pr: dict[str, Any]) -> list[dict[str, Any]]:
    terms = sorted(set(TOKEN_RE.findall((pr["title"] + " " + pr["head_branch"]).lower())))
    changed = set(pr["files"])
    basenames = {Path(path).name for path in changed}
    matches: list[dict[str, Any]] = []
    for directory in ARTIFACT_DIRS:
        for path in sorted(root.glob("*/"+directory+"/**/*")) + sorted((root / directory).glob("**/*")):
            if path.suffix not in {".html", ".md"} or path.name.startswith("_template"):
                continue
            text = path.read_text(errors="replace")
            lower = text.lower()
            signals: list[dict[str, Any]] = []
            score = 0
            if pr["head_branch"] in text:
                score += add_signal(signals, 60, "exact-branch", pr["head_branch"])
            if pr["url"] in text:
                score += add_signal(signals, 60, "exact-pr-url", pr["url"])
            if re.search(rf"(?:PR\s*#?|pull/)\s*{pr['number']}\b", text, re.I):
                score += add_signal(signals, 30, "pr-number", str(pr["number"]))
            if pr["head_sha"] in text:
                score += add_signal(signals, 50, "exact-head-sha", pr["head_sha"])
            path_hits = sorted(item for item in changed if item in text)
            base_hits = sorted(item for item in basenames if item in text)
            for item in path_hits[:10]:
                score += add_signal(signals, 8, "changed-path", item)
            for item in (set(base_hits) - {Path(hit).name for hit in path_hits}):
                score += add_signal(signals, 3, "changed-basename", item)
            term_hits = [term for term in terms if term in lower]
            if term_hits:
                points = min(15, len(term_hits))
                score += add_signal(signals, points, "topic-terms", ",".join(term_hits))
            if score:
                matches.append({"path": str(path.resolve()), "score": score, "signals": signals})
    return sorted(matches, key=lambda item: (-item["score"], item["path"]))


def cortex_matches(
    pr: dict[str, Any], server: str | None, worktree: Path | None = None
) -> list[dict[str, Any]]:
    if not server:
        return []
    env = os.environ.copy()
    # A bare PR number is too weak across a fleet-wide transcript index: every
    # repository can have a PR #13. Branch, SHA, and full URL are repository-bound.
    queries = [pr["head_branch"], pr["head_sha"], pr["url"]]
    if worktree:
        queries.extend([str(worktree), worktree.name])
    found: dict[str, dict[str, Any]] = {}
    for query in queries:
        phrase = json.dumps(query)
        try:
            data = run_json(
                ["cortex", "--server", server, "sessions", "search", phrase,
                 "--limit", "100", "--json"], env=env
            )
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        for item in data.get("sessions", []):
            key = item["session_key"]
            current = found.setdefault(key, {**item, "queries": []})
            current["queries"].append(query)
    return sorted(found.values(), key=lambda item: (-len(item["queries"]), item["first_seen"]))


def discover_cortex(
    pr: dict[str, Any], explicit_server: str | None, worktree: Path | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Query Cortex when explicitly configured and retain an honest query receipt."""
    server = explicit_server or os.environ.get("CORTEX_URL")
    if not server:
        return [], {
            "status": "NOT CONFIGURED",
            "session_count": 0,
            "reason": "No --cortex-server argument or CORTEX_URL was available; Cortex was not queried.",
        }
    if not os.environ.get("CORTEX_API_TOKEN"):
        return [], {
            "status": "BLOCKED",
            "session_count": 0,
            "server": server,
            "reason": "CORTEX_API_TOKEN was unavailable; Cortex was not queried.",
        }
    sessions = cortex_matches(pr, server, worktree)
    return sessions, {
        "status": "PASS",
        "session_count": len(sessions),
        "server": server,
        "queries": [pr["head_branch"], pr["head_sha"], pr["url"]] + (
            [str(worktree), worktree.name] if worktree else []
        ),
        "boundary": "Search results are reference evidence until paired with a local transcript or structured Git attribution.",
    }


def local_transcripts(
    pr: dict[str, Any], roots: list[Path], worktree: Path | None = None
) -> list[dict[str, Any]]:
    existing = [str(path) for path in roots if path.exists()]
    if not existing:
        return []
    weighted_terms = {
        pr["head_branch"]: 4, pr["head_sha"]: 4, pr["url"]: 5,
        f"pull/{pr['number']}": 1,
    }
    if worktree:
        weighted_terms[str(worktree)] = 6
    terms = list(weighted_terms)
    pattern = "|".join(re.escape(term) for term in terms)
    result = subprocess.run(
        ["rg", "-l", "--hidden", "--glob", "*.jsonl", pattern, *existing],
        text=True, capture_output=True, check=False,
    )
    matches = []
    for raw in result.stdout.splitlines():
        path = Path(raw)
        text = path.read_text(errors="replace")
        hits = [term for term in terms if term in text]
        score = sum(weighted_terms[term] for term in hits)
        if score < 4:
            continue
        session_id = path.stem
        project = None
        tool = "codex" if "/.codex/" in raw else "claude"
        first_seen = last_seen = None
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = item.get("sessionId") or item.get("payload", {}).get("id") or session_id
            project = item.get("cwd") or item.get("payload", {}).get("cwd") or project
            timestamp = item.get("timestamp")
            if timestamp:
                first_seen = first_seen or timestamp
                last_seen = timestamp
            if project and first_seen and session_id != path.stem:
                break
        matches.append({
            "path": str(path.resolve()), "tool": tool, "session_id": session_id,
            "project": project, "first_seen": first_seen, "last_seen": last_seen,
            "matched_terms": hits, "score": score,
            "is_subagent_transcript": "/subagents/" in raw,
        })
    return sorted(matches, key=lambda item: (-item["score"], item["path"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--artifacts-root", type=Path, default=Path(os.environ.get('ARTIFACTS_ROOT',str(Path.home()/'artifacts'))))
    parser.add_argument("--cortex-server", help="HTTP API URL; token comes from CORTEX_API_TOKEN")
    parser.add_argument("--worktree", type=Path,
                        help="Absolute PR worktree path; used as a strong session-lineage key")
    parser.add_argument("--session-root", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worktree and not args.worktree.is_absolute():
        parser.error("--worktree must be absolute")
    pr = pr_context(args.repository, args.pr)
    cortex_sessions, cortex_query = discover_cortex(pr, args.cortex_server, args.worktree)
    result = {
        "schema": 1,
        "pr": pr,
        "artifact_matches": match_artifacts(args.artifacts_root.resolve(), pr),
        "cortex_query": cortex_query,
        "cortex_sessions": cortex_sessions,
        "local_transcripts": local_transcripts(
            pr, args.session_root or list(SESSION_ROOTS), args.worktree
        ),
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
