#!/usr/bin/env python3
"""Generate, evidence-link, validate, and seal one GitHub PR report draft."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from _app.projects import assert_project, brand_for, library_root
from _app.pr_reports import branch_stem


def run(*args: object, capture: bool = False) -> str:
    result = subprocess.run(
        [str(arg) for arg in args], check=True, text=True,
        capture_output=capture, env=os.environ.copy(),
    )
    return result.stdout if capture else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--cortex-server")
    parser.add_argument("--primary-session-id", action="append", default=[])
    parser.add_argument("--unraid-related", action="store_true")
    args = parser.parse_args()
    if not args.worktree.is_absolute() or not args.worktree.is_dir():
        parser.error("--worktree must be an existing absolute directory")

    output_root = library_root()
    project = assert_project(output_root, args.repository)
    evidence_dir = project / "pr-reports" / "evidence"
    if evidence_dir.parent.is_symlink() or evidence_dir.is_symlink():
        raise ValueError("PR evidence directories must not be symlinks")
    try:
        family = brand_for(args.repository, worktree=args.worktree, unraid_related=args.unraid_related)
    except ValueError:
        family = brand_for(args.repository, unraid_related=args.unraid_related)
    preliminary = Path(tempfile.mkstemp(prefix=f"pr-{args.pr}-", suffix=".json")[1])
    try:
        command = [sys.executable, HERE / "discover-pr-context.py",
                   "--repository", args.repository, "--pr", args.pr,
                   "--worktree", args.worktree, "--artifacts-root", output_root, "--output", preliminary]
        if args.cortex_server:
            command += ["--cortex-server", args.cortex_server]
        run(*command)
        context = json.loads(preliminary.read_text())
        pr = context["pr"]
        stem = branch_stem(pr["head_branch"])

        output = run(
            sys.executable, HERE / "new-pr-report.py",
            "--repository", args.repository,
            "--branch", pr["head_branch"],
            "--base", f'{pr["base_branch"]} @ {pr["base_sha"]}',
            "--head-sha", pr["head_sha"],
            "--merge-base", pr["merge_base"],
            "--worktree", args.worktree,
            "--pr", f'#{pr["number"]} · {pr["state"]} · {pr["url"]}',
            "--topic", stem,
            "--github-authoritative",
            "--root", output_root,
            *(["--unraid-related"] if family=="unraid" else []),
            capture=True,
        )
        report, manifest = [Path(line) for line in output.strip().splitlines()[-2:]]
        durable_dir = evidence_dir / report.stem
        durable_dir.mkdir(parents=True, exist_ok=False)
        context_path = durable_dir / "context.json"
        context_path.write_text(json.dumps(context, indent=2) + "\n")
        run(
            sys.executable, HERE / "record-pr-evidence.py",
            "--manifest", manifest, "--id", "E-001", "--kind", "discovery-context",
            "--file", context_path, "--producer", "generate-pr-report-draft.py",
            "--command", f"discover-pr-context.py --repository {args.repository} --pr {args.pr}",
            "--source-sha", pr["head_sha"], "--applies-to", "head",
            "--cwd", args.worktree, "--state", "PASS",
        )
        session_path = durable_dir / "session-evidence.json"
        session_command = [
            sys.executable, HERE / "build-pr-session-evidence.py",
            "--context", context_path, "--output", session_path,
        ]
        for session_id in args.primary_session_id:
            session_command += ["--primary-session-id", session_id]
        run(*session_command)
        run(
            sys.executable, HERE / "record-pr-evidence.py",
            "--manifest", manifest, "--id", "E-003", "--kind", "session-lineage-analysis",
            "--file", session_path, "--producer", "build-pr-session-evidence.py",
            "--command", "complete secret-scrubbed scan of selected PR transcript lineage",
            "--source-sha", pr["head_sha"], "--applies-to", "external",
            "--cwd", ROOT, "--state", "PASS",
        )
        state_path = durable_dir / "pr-state.json"
        run(
            sys.executable, HERE / "snapshot-pr-state.py",
            "--pr", pr["url"], "--manifest", manifest, "--id", "E-002",
            "--output", state_path, "--source-sha", pr["head_sha"],
            "--cwd", args.worktree,
        )
        run(sys.executable, HERE / "seed-pr-report.py", report, "--context", context_path,
            "--session-evidence", session_path)
        run(sys.executable, HERE / "sync-pr-report-ledgers.py", report)
        with tempfile.NamedTemporaryFile("w", delete=False) as changed:
            changed.write("\n".join(pr["files"]) + "\n")
            changed_path = Path(changed.name)
        try:
            run(sys.executable, HERE / "seal-pr-report.py",
                "--current-head", pr["head_sha"],
                "--current-merge-base", pr["merge_base"],
                "--changed-files", changed_path, report)
            run(sys.executable, HERE / "seal-pr-report.py", "--verify",
                "--current-head", pr["head_sha"],
                "--current-merge-base", pr["merge_base"],
                "--changed-files", changed_path, report)
        finally:
            changed_path.unlink(missing_ok=True)
        print(report.resolve())
        return 0
    finally:
        preliminary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
