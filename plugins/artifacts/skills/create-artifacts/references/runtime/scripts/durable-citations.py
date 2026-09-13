#!/usr/bin/env python3
"""Repoint citations that name a temporary worktree at the durable repository.

A link into `.claude/worktrees/<id>/` dies when the worktree is pruned, and
cannot be rewritten to a remote base on export because the worktree segment is
not part of the repository. This resolves each worktree to its main checkout via
git and rewrites the citation — but only when the durable target actually
exists, so a rewrite can never invent a path.

Run:  scripts/durable-citations.py [--check]
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKTREE = re.compile(
    r'(?P<scheme>href="file://)(?P<prefix>/[^"#]*?)/\.claude/worktrees/(?P<id>[^/]+)/(?P<rest>[^"#]*)')


def main_checkout(path):
    """The main working tree a worktree belongs to, or None."""
    try:
        common = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None
    return Path(common).parent if common.endswith("/.git") else None


def main():
    check = "--check" in sys.argv
    roots, rewritten, skipped, touched = {}, 0, [], []

    for artifact in sorted(ROOT.glob("*/*.html")):
        if artifact.name.startswith("_"):
            continue
        source = artifact.read_text(encoding="utf-8")
        original = source

        def repoint(match):
            nonlocal rewritten
            worktree = Path(match.group("prefix")) / ".claude" / "worktrees" / match.group("id")
            if worktree not in roots:
                roots[worktree] = main_checkout(worktree)
            base = roots[worktree]
            if base is None:
                skipped.append((match.group(0), "worktree does not resolve to a checkout"))
                return match.group(0)
            durable = base / match.group("rest")
            if not durable.exists():
                skipped.append((match.group(0), "durable target does not exist"))
                return match.group(0)
            rewritten += 1
            return match.group("scheme") + str(durable)

        source = WORKTREE.sub(repoint, source)
        if source != original:
            touched.append(artifact.relative_to(ROOT))
            if not check:
                artifact.write_text(source, encoding="utf-8")

    verb = "would repoint" if check else "repointed"
    for rel in touched:
        print(f"  {verb} {rel}")
    print(f"{rewritten} citation(s) {verb}, {len(skipped)} left alone")
    for citation, why in skipped[:5]:
        print(f"  kept: {why} — {citation[:90]}")
    return 1 if (check and touched) else 0


if __name__ == "__main__":
    sys.exit(main())
