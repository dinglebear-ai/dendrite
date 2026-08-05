#!/usr/bin/env python3
"""Refresh the layered homelab context sources and write a source manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
LEGACY_GENERATOR = SKILL_DIR / "scripts" / "generate-homelab-report.py"
DEFAULT_DOCS_ROOT = Path(os.environ.get("HOMELAB_DOCS_ROOT", Path.home() / "docs")).expanduser()
DEFAULT_OUTPUT_DIR = Path.home() / ".homelab"
COLLECTORS = (
    "proxies.sh",
    "docker.sh",
    "devices.sh",
    "unraid.sh",
    "tailscale.sh",
    "unifi.sh",
    "mcp.sh",
    "health.sh",
)
SOURCE_PATTERNS = (
    "generated/homelab/*.md",
    "generated/homelab/*.json",
    "generated/net/*.md",
    "generated/net/*.json",
    "generated/mcp/*.md",
    "generated/mcp/*.json",
    "generated/dev/projects*.md",
    "generated/dev/projects*.json",
    "decisions/index.md",
    "maintenance/index.md",
    "reports/index.md",
    "plans/index.md",
    "sessions/index.md",
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run(command: list[str], *, env: dict[str, str] | None = None, timeout: int = 900) -> dict[str, Any]:
    started = now_iso()
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return {
            "command": command,
            "started_at": started,
            "finished_at": now_iso(),
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "started_at": started,
            "finished_at": now_iso(),
            "returncode": 124,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "error": "timeout",
        }
    except OSError as exc:
        return {
            "command": command,
            "started_at": started,
            "finished_at": now_iso(),
            "returncode": 127,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "error": type(exc).__name__,
        }


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove command output from persisted manifests while retaining diagnostics metadata."""
    compact = {
        key: value
        for key, value in result.items()
        if key not in {"stdout_tail", "stderr_tail"}
    }
    compact["stdout_bytes"] = len(result.get("stdout_tail", "").encode("utf-8"))
    compact["stderr_bytes"] = len(result.get("stderr_tail", "").encode("utf-8"))
    return compact


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": stat.st_size,
        "modified_at": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "sha256": sha256(path),
    }


def git_state(root: Path | None) -> dict[str, Any] | None:
    if root is None or not (root / ".git").exists():
        return None
    head = run(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=30)
    branch = run(["git", "-C", str(root), "branch", "--show-current"], timeout=30)
    status = run(["git", "-C", str(root), "status", "--short"], timeout=30)
    remote = run(["git", "-C", str(root), "remote", "get-url", "origin"], timeout=30)
    return {
        "root": str(root),
        "head": head["stdout_tail"].strip() if head["returncode"] == 0 else None,
        "branch": branch["stdout_tail"].strip() if branch["returncode"] == 0 else None,
        "remote": remote["stdout_tail"].strip() if remote["returncode"] == 0 else None,
        "dirty": bool(status["stdout_tail"].strip()) if status["returncode"] == 0 else None,
        "status": status["stdout_tail"].splitlines() if status["returncode"] == 0 else [],
    }


def discover_homelab_repo(explicit: Path | None) -> Path | None:
    candidates = [
        explicit,
        Path(os.environ["HOMELAB_REPO"]).expanduser() if os.environ.get("HOMELAB_REPO") else None,
        Path.home() / "workspace" / "homelab",
        Path.home() / "workspace" / "compose",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate.resolve()
    return None


def collect_sources(docs_root: Path) -> list[dict[str, Any]]:
    paths: set[Path] = set()
    for pattern in SOURCE_PATTERNS:
        paths.update(path for path in docs_root.glob(pattern) if path.is_file())
    return [file_record(path) for path in sorted(paths)]


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--homelab-repo", type=Path)
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--skip-live-map", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    docs_root = args.docs_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    repo = discover_homelab_repo(args.homelab_repo)
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    if not args.skip_collect:
        env = dict(os.environ)
        env["DOCS_ROOT"] = str(docs_root)
        env["HOMELAB_DOCS_ROOT"] = str(docs_root)
        for name in COLLECTORS:
            script = docs_root / "scripts" / name
            if not script.exists():
                results.append({"collector": name, "returncode": 127, "error": "missing"})
                failures.append(name)
                continue
            result = run([str(script)], env=env)
            persisted = compact_result(result)
            persisted["collector"] = name
            results.append(persisted)
            if result["returncode"] != 0:
                failures.append(name)
                if args.strict:
                    break

    legacy_result: dict[str, Any] | None = None
    if not args.skip_live_map and (not args.strict or not failures):
        command = [
            sys.executable,
            str(LEGACY_GENERATOR),
            "--output",
            str(output_dir / "homelab.md"),
            "--json-output",
            str(output_dir / "homelab.json"),
            "--html-output",
            str(output_dir / "index.html"),
            "--no-serve",
        ]
        raw_legacy_result = run(command)
        legacy_result = compact_result(raw_legacy_result)
        if raw_legacy_result["returncode"] != 0:
            failures.append("generate-homelab-report.py")

    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "docs_root": str(docs_root),
        "output_dir": str(output_dir),
        "declared_repository": git_state(repo),
        "collectors": results,
        "compiled_map": legacy_result,
        "sources": collect_sources(docs_root),
        "failures": failures,
    }
    manifest = output_dir / "context-sources.json"
    write_json_atomic(manifest, payload)

    print(f"context manifest: {manifest}")
    print(f"sources: {len(payload['sources'])}")
    if failures:
        print("failed collectors: " + ", ".join(failures), file=sys.stderr)
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
