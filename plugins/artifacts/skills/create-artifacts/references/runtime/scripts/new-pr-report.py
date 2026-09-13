#!/usr/bin/env python3
"""Create a collision-safe PR report from the canonical repository template."""
from __future__ import annotations

import argparse
import html
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from _app.projects import assert_project, brand_for, library_root, template_path
from _app.asset_files import embed_fonts
from _app.contracts import registry
from _app.pr_reports import artifact_id, branch_stem, repository_dir  # noqa: E402
def meta(source: str, name: str) -> str:
    found = re.search(r'<meta name="artifact\.' + re.escape(name) + r'" content="([^"]*)">', source)
    return html.unescape(found.group(1)) if found else ""


def set_meta(source: str, name: str, value: str) -> str:
    escaped = html.escape(value, quote=True)
    pattern = r'(<meta name="artifact\.' + re.escape(name) + r'" content=")[^"]*(">)'
    updated, count = re.subn(pattern, lambda match: match.group(1) + escaped + match.group(2), source, count=1)
    if count != 1:
        raise ValueError("canonical template is missing artifact." + name)
    return updated


def destination(root: Path, repository: str, branch: str, head_sha: str) -> Path:
    project = assert_project(root, repository)
    folder = project / "pr-reports"
    if folder.is_symlink():
        raise ValueError("artifact folder must not be a symlink")
    for previous in folder.glob("*.html"):
        if meta(previous.read_text(), "head").split("@", 1)[0].strip() == branch:
            raise FileExistsError("report already exists for this branch: " + str(previous))
    repo_dir = project.name
    branch_file = datetime.now().strftime("%m-%d-%y") + "-" + branch_stem(branch) + ".html"
    candidate = root / repo_dir / "pr-reports" / branch_file
    if not candidate.exists():
        return candidate
    existing_branch = meta(candidate.read_text(), "head").split("@", 1)[0].strip()
    if existing_branch == branch:
        raise FileExistsError("report already exists for this branch: " + str(candidate))
    suffix = head_sha[:8].lower()
    if not re.fullmatch(r"[0-9a-f]{8}", suffix):
        raise ValueError("a colliding normalized branch requires at least 8 hexadecimal head SHA characters")
    collision = candidate.with_name(candidate.stem + "--" + suffix + ".html")
    if collision.exists():
        raise FileExistsError("collision-safe report already exists: " + str(collision))
    return collision


def git(worktree: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(worktree), *args], text=True,
                            capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git identity check failed")
    return result.stdout.strip()


def verify_live(args) -> str:
    worktree = Path(args.worktree).resolve()
    if args.github_authoritative:
        if not worktree.is_dir():
            raise ValueError("worktree does not exist")
        return (
            "VERIFIED — GitHub API snapshot is authoritative for PR/base/head/merge-base; "
            "the absolute local worktree path exists but local Git identity was deliberately not invoked"
        )
    caveats = []
    try:
        if not worktree.is_dir():
            raise ValueError("worktree does not exist")
        if Path(git(worktree, "rev-parse", "--show-toplevel")).resolve() != worktree:
            raise ValueError("worktree is not the physical repository root")
        if git(worktree, "branch", "--show-current") != args.branch:
            raise ValueError("live branch differs from --branch")
        if git(worktree, "rev-parse", "HEAD").lower() != args.head_sha.lower():
            raise ValueError("live HEAD differs from --head-sha")
        base_ref, base_sha = (part.strip() for part in args.base.rsplit("@", 1))
        resolved = None
        remotes = git(worktree, "remote").splitlines()
        target_remote = args.target_remote if args.target_remote in remotes else None
        for candidate in remotes:
            remote_url = git(worktree, "remote", "get-url", candidate)
            parsed = re.fullmatch(r'(?:git@github\.com:|https?://github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?', remote_url, re.I)
            if parsed and (parsed.group(1)+"/"+parsed.group(2)).lower() == args.repository.lower():
                target_remote = candidate; break
        if not target_remote: raise ValueError("no GitHub remote matches target repository")
        for ref in (target_remote + "/" + base_ref, base_ref):
            try:
                resolved = git(worktree, "rev-parse", "--verify", ref)
                break
            except ValueError:
                pass
        if resolved is None or resolved.lower() != base_sha.lower():
            raise ValueError("declared base ref does not resolve to supplied base SHA")
        if git(worktree, "merge-base", base_sha, args.head_sha).lower() != args.merge_base.lower():
            raise ValueError("live merge base differs from --merge-base")
        remote = git(worktree, "remote", "get-url", target_remote)
        match = re.fullmatch(r'(?:git@github\.com:|https?://github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?', remote, re.I)
        if not match or (match.group(1)+"/"+match.group(2)).lower() != args.repository.lower():
            raise ValueError("target remote does not match --repository")
        return "VERIFIED"
    except ValueError as error:
        if not args.allow_unverified:
            raise
        caveats.append(str(error))
        return "UNVERIFIED — " + "; ".join(caveats)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub org/repo")
    parser.add_argument("--branch", required=True, help="Exact head branch")
    parser.add_argument("--base", required=True, help="Base branch @ full SHA")
    parser.add_argument("--head-sha", required=True, help="Full head SHA")
    parser.add_argument("--merge-base", required=True, help="Full merge-base SHA")
    parser.add_argument("--worktree", required=True, help="Absolute physical worktree path")
    parser.add_argument("--target-remote", default="upstream", help="Remote for the target repository; matching remotes are auto-discovered")
    parser.add_argument("--pr", default="not-yet-created", help="PR URL/number/state")
    parser.add_argument("--topic", required=True, help="Artifact topic slug")
    parser.add_argument("--started", help="ISO-8601 start time; defaults to now")
    parser.add_argument("--allow-unverified", action="store_true",
                        help="Create with an explicit provenance caveat when live Git checks cannot run")
    parser.add_argument("--github-authoritative", action="store_true",
                        help="Use a fresh GitHub API snapshot as identity authority without invoking local Git")
    parser.add_argument("--unraid-related", action="store_true", help="Artifact subject is part of the Unraid ecosystem")
    parser.add_argument("--root", type=Path, default=library_root(), help="Artifact package root")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", args.repository, re.I):
        parser.error("--repository must be owner/repository")
    if not Path(args.worktree).is_absolute():
        parser.error("--worktree must be absolute")
    for label, value in (("head", args.head_sha), ("merge-base", args.merge_base)):
        if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
            parser.error("--" + label + " must be a full 40-character SHA")
    if not re.fullmatch(r".+\s+@\s+[0-9a-fA-F]{40}", args.base):
        parser.error("--base must be '<branch> @ <full SHA>'")

    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    provenance = verify_live(args)
    output = destination(args.root.resolve(), args.repository, args.branch, args.head_sha)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_suffix(".evidence.jsonl").resolve()
    routing_worktree = None if args.github_authoritative else args.worktree
    if args.allow_unverified:
        probe = subprocess.run(["git", "-C", args.worktree, "rev-parse", "--git-dir"], capture_output=True)
        if probe.returncode: routing_worktree = None
    family=brand_for(args.repository,worktree=routing_worktree,unraid_related=args.unraid_related)
    source=template_path("pr-reports",family).read_text()
    source=source.replace("{{Project}}", html.escape(args.repository))
    source=source.replace("</title>", '</title>\n<meta name="artifact.brand" content="'+family+'">\n<meta name="artifact.unraid-related" content="'+str(family=='unraid').lower()+'">')
    source=source.replace('</title>','</title>\n<meta name="artifact.contract-version" content="'+registry()['version']+'">')
    values = {
        "id": artifact_id(args.repository, args.branch), "date": now[:10],
        "topic": args.topic, "target": args.head_sha.lower(), "branch": args.branch,
        "worktree": str(Path(args.worktree).resolve()), "repository": args.repository,
        "base": args.base, "head": args.branch + " @ " + args.head_sha.lower(),
        "merge-base": args.merge_base.lower(), "pr": args.pr,
        "started": args.started or now, "updated": now,
        "evidence-manifest": str(manifest), "report-digest": "UNSEALED",
        "evidence-manifest-digest": "UNSEALED",
        "provenance-status": provenance,
    }
    for name, value in values.items():
        source = set_meta(source, name, value)
    source = source.replace("{{Repository}}", html.escape(args.repository)).replace(
        "{{Branch}}", html.escape(args.branch))
    source = source.replace("<td>1</td><td>{{ISO-8601}}</td><td>{{full SHA}}</td><td>{{IDs}}</td><td>{{Why}}</td><td>{{digest or initial}}</td>",
        "<td>1</td><td>" + html.escape(now) + "</td><td>" + args.head_sha.lower()
        + "</td><td>initial</td><td>Created by new-pr-report.py</td><td>initial</td>")
    if output.exists() or manifest.exists():
        raise FileExistsError("refusing existing report or manifest destination")
    source = embed_fonts(source)
    created = []
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(source)
        created.append(output)
        with manifest.open("x", encoding="utf-8"):
            pass
        created.append(manifest)
        compiled = subprocess.run([
            sys.executable, str(Path(__file__).with_name("pr-report.py")),
            "compile", str(output),
        ], capture_output=True, text=True, check=False)
        if compiled.returncode:
            raise RuntimeError(compiled.stderr.strip() or "machine-manifest compilation failed")
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    print(output)
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
