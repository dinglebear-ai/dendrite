#!/usr/bin/env python3
"""Build a bounded, secret-scrubbed PR session-lineage evidence record."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization|api[-_ ]?key|password|secret|token)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)
CATEGORIES = {
    "planning": ("plan", "proposal", "requirement", "must-have", "nice-to-have"),
    "implementation": ("implement", "change", "patch", "refactor", "commit"),
    "testing": ("test", "verify", "validation", "passed", "failed", "tower", "appliance"),
    "review": ("review", "finding", "remediation", "risk"),
    "publication": ("push", "pull request", "pr #", "github", "rebase"),
    "debugging": ("debug", "root cause", "failure", "error"),
}


def scrub(value: str) -> str:
    value = value.replace("\x00", "")
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]" if match.lastindex == 2 else "[REDACTED]", value)
    return re.sub(r"\s+", " ", value).strip()


def text_fragments(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from text_fragments(item)
    elif isinstance(value, dict):
        for key in ("text", "input_text", "output_text", "content", "message"):
            if key in value:
                yield from text_fragments(value[key])


def relevant_categories(text: str, terms: list[str]) -> list[str]:
    lower = text.lower()
    if not any(term.lower() in lower for term in terms if term):
        return []
    return [name for name, needles in CATEGORIES.items() if any(needle in lower for needle in needles)] or ["lineage"]


def scan_transcript(path: Path, terms: list[str], max_excerpts: int, excerpt_chars: int) -> dict[str, Any]:
    snapshot_bytes = path.stat().st_size
    digest = hashlib.sha256()
    records = invalid = 0
    boundary_partial_record = False
    message_roles: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    excerpts: list[dict[str, Any]] = []
    first_seen = last_seen = None
    with path.open("rb") as source:
        remaining = snapshot_bytes
        while remaining:
            raw = source.readline(remaining)
            if not raw:
                break
            remaining -= len(raw)
            digest.update(raw)
            if remaining == 0 and not raw.endswith(b"\n"):
                boundary_partial_record = True
                continue
            records += 1
            try:
                item = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                invalid += 1
                continue
            timestamp = item.get("timestamp")
            if timestamp:
                first_seen = first_seen or timestamp
                last_seen = timestamp
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            payload_type = payload.get("type")
            if item.get("type") == "response_item" and payload_type in {"function_call", "custom_tool_call"}:
                tools[str(payload.get("name") or "unknown")] += 1
            if payload_type not in {"message", "agent_message"}:
                continue
            role = str(payload.get("role") or ("agent" if payload_type == "agent_message" else "unknown"))
            message_roles[role] += 1
            text = scrub(" ".join(text_fragments(payload.get("content"))))
            matched = relevant_categories(text, terms)
            if not matched:
                continue
            categories.update(matched)
            if len(excerpts) < max_excerpts:
                excerpts.append({
                    "timestamp": timestamp,
                    "role": role,
                    "categories": matched,
                    "excerpt": text[:excerpt_chars],
                    "truncated": len(text) > excerpt_chars,
                })
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "source_sha256": digest.hexdigest(),
        "snapshot_bytes": snapshot_bytes,
        "source_bytes_at_finish": stat.st_size,
        "source_grew_during_capture": stat.st_size > snapshot_bytes,
        "full_scan": True,
        "full_scan_boundary": f"complete transcript prefix through byte {snapshot_bytes}",
        "records_scanned": records,
        "invalid_json_lines": invalid,
        "boundary_partial_record": boundary_partial_record,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "message_roles": dict(sorted(message_roles.items())),
        "tool_calls": dict(tools.most_common()),
        "matched_categories": dict(categories.most_common()),
        "matched_excerpts": excerpts,
        "excerpt_limit": max_excerpts,
    }


def session_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("tool") or "unknown").lower(), str(item.get("session_id") or "unknown")


def combine_candidates(context: dict[str, Any], primary_ids: set[str]) -> list[dict[str, Any]]:
    combined: dict[tuple[str, str], dict[str, Any]] = {}
    for item in context.get("local_transcripts", []):
        key = session_key(item)
        current = combined.setdefault(key, {
            "tool": key[0], "session_id": key[1], "sources": [], "paths": [],
            "score": 0, "is_subagent_transcript": True,
        })
        current["sources"].append("local")
        current["paths"].append(str(item["path"]))
        current["score"] = max(current["score"], int(item.get("score") or 0))
        current["is_subagent_transcript"] = current["is_subagent_transcript"] and bool(item.get("is_subagent_transcript"))
        for field in ("project", "first_seen", "last_seen"):
            current[field] = current.get(field) or item.get(field)
    for item in context.get("cortex_sessions", []):
        key = session_key(item)
        current = combined.setdefault(key, {
            "tool": key[0], "session_id": key[1], "sources": [], "paths": [],
            "score": 0, "is_subagent_transcript": False,
        })
        current["sources"].append("cortex")
        current["score"] += 3 + len(item.get("queries", []))
        current["cortex"] = {name: item.get(name) for name in (
            "session_key", "hostname", "project", "first_seen", "last_seen",
            "event_count", "match_count", "queries", "best_snippet",
        ) if item.get(name) is not None}
        for field in ("project", "first_seen", "last_seen"):
            current[field] = current.get(field) or item.get(field)
    for item in combined.values():
        item["sources"] = sorted(set(item["sources"]))
        item["paths"] = sorted(set(item["paths"]))
        item["classification"] = "primary" if item["session_id"] in primary_ids else (
            "supporting-subagent" if item["is_subagent_transcript"] else "candidate"
        )
        item["rank_score"] = item["score"] + (30 if item["classification"] == "primary" else 0) - (
            10 if item["is_subagent_transcript"] else 0
        ) + (5 if len(item["sources"]) > 1 else 0)
    return sorted(combined.values(), key=lambda item: (-item["rank_score"], item["session_id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--primary-session-id", action="append", default=[])
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--max-excerpts", type=int, default=40)
    parser.add_argument("--excerpt-chars", type=int, default=600)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output already exists; session evidence is immutable")
    context = json.loads(args.context.read_text())
    primary_ids = set(args.primary_session_id)
    candidates = combine_candidates(context, primary_ids)
    selected = [item for item in candidates if item["classification"] == "primary"]
    if not selected:
        selected = [item for item in candidates if not item["is_subagent_transcript"]][:args.max_sessions]
    else:
        selected = selected[:args.max_sessions]
    pr = context["pr"]
    terms = [pr["head_branch"], pr["head_sha"], pr["url"], str(pr["number"]), "unassigned device"]
    analyzed = []
    for item in selected:
        local_paths = [Path(value) for value in item["paths"] if Path(value).is_file()]
        analysis = scan_transcript(local_paths[0], terms, args.max_excerpts, args.excerpt_chars) if local_paths else None
        analyzed.append({**item, "analysis": analysis})
    result = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_context": str(args.context.resolve()),
        "source_context_sha256": hashlib.sha256(args.context.read_bytes()).hexdigest(),
        "pr": {name: pr[name] for name in ("repository", "number", "url", "head_branch", "head_sha")},
        "cortex_query": context.get("cortex_query", {
            "status": "legacy-context", "session_count": len(context.get("cortex_sessions", []))
        }),
        "denominator": {
            "local_candidates": len(context.get("local_transcripts", [])),
            "cortex_candidates": len(context.get("cortex_sessions", [])),
            "deduplicated_sessions": len(candidates),
            "selected_sessions": len(analyzed),
            "primary_session_ids": sorted(primary_ids),
        },
        "sessions": analyzed,
        "excluded_sessions": [
            {name: item[name] for name in ("tool", "session_id", "classification", "rank_score")}
            for item in candidates if item not in selected
        ],
        "proof_boundary": (
            "Every selected local transcript snapshot was scanned completely through its recorded byte boundary and content-bound by SHA-256. "
            "Only secret-scrubbed, scope-matching message excerpts and tool-name counts are retained; "
            "tool arguments, tool outputs, hidden reasoning, and unmatched conversation content are excluded. "
            "Cortex-only snippets are reference evidence and do not prove checkout provenance."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
