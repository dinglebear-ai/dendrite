#!/usr/bin/env python3
"""Check every artifact against the rules in _app/validate.py.

The rules live in one module so this and the index build cannot disagree; this
is the command-line face of them. Exit 0 when clean, 1 on any error. Warnings
never fail the run.

Run:  scripts/lint-artifacts.py [--quiet]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from _app import validate  # noqa: E402
from _app.catalog import CATEGORIES, load_catalog  # noqa: E402

SKIP = {"CLAUDE.md", "AGENTS.md", "README.md"}


def folder_issues(root):
    """Structural expectations about the taxonomy itself, which the catalog does
    not check because it only ever looks at files it can index."""
    issues = []
    for name in CATEGORIES:
        folder = root / name
        if not folder.is_dir():
            issues.append(validate.issue("error", name + "/", "taxonomy folder is missing",
                                         "TAXONOMY"))
            continue
        if not (folder / "CLAUDE.md").exists():
            issues.append(validate.issue("error", name + "/",
                                         "no CLAUDE.md — the index reads its opening paragraph",
                                         "TAXONOMY"))
        if not (folder / "AGENTS.md").is_symlink():
            issues.append(validate.issue("error", name + "/",
                                         "AGENTS.md is not a symlink to CLAUDE.md", "TAXONOMY"))
        if not list(folder.glob("_template.*")):
            issues.append(validate.issue("error", name + "/", "no _template.* to copy",
                                         "TAXONOMY"))
        for path in sorted(folder.iterdir()):
            if (not path.is_file() or path.name in SKIP
                    or path.name.startswith((".", "_", "test_"))):
                continue
            if path.suffix in (".sh", ".py", ".exs"):
                head = "\n".join(path.read_text(errors="replace").splitlines()[:40])
                rel = name + "/" + path.name
                if path.suffix == ".sh" and "set -euo pipefail" not in head:
                    issues.append(validate.issue("error", rel,
                                                 "shell harness without `set -euo pipefail`",
                                                 "HARNESS-STRICT", 1))
    return issues


def collect(root):
    """Every issue for the library, and how many artifacts were examined."""
    catalog = load_catalog(root)
    sources = {item["href"]: item["source"]
               for item in catalog["items"] if item.get("source")}
    issues = (list(catalog["issues"]) + validate.check_design_tokens(sources)
              + folder_issues(root))
    return issues, len(catalog["items"])


def main():
    import subprocess
    from _app.projects import SKILL
    return subprocess.call([sys.executable,str(SKILL/'scripts/artifacts.py'),'validate',*sys.argv[1:]])

if __name__ == "__main__":
    sys.exit(main())
