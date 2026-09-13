#!/usr/bin/env python3
"""Write the shared style blocks into every artifact, idempotently.

Each artifact carries its own inlined stylesheet, so anything that must hold
across the library has to be written into all of them:

  _app/theme.py       the dark palette, inserted after the :root tokens
  _app/typography.py  the monospace restriction, appended after the artifact's
                      own rules so it wins on order rather than specificity

It also drops the hardcoded data-theme="light" from <html>, so the system
preference decides unless a reader pins one.

Safe to re-run: each block is delimited by markers and replaced wholesale.

Run:  scripts/apply-styles.py            # every artifact and template
      scripts/apply-styles.py --check    # report drift, change nothing
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from _app.projects import library_root
ROOT = library_root()

from _app.theme import CSS as THEME_CSS  # noqa: E402
from _app.theme import MARK_CLOSE, MARK_OPEN  # noqa: E402
from _app.typography import CSS as TYPE_CSS  # noqa: E402
from _app.typography import MARK_CLOSE as TYPE_CLOSE  # noqa: E402
from _app.typography import MARK_OPEN as TYPE_OPEN  # noqa: E402

SKIP_DIRS = {".git", "dist", "_tests", "node_modules"}
BLOCK = re.compile(r"\n?" + re.escape(MARK_OPEN) + ".*?" + re.escape(MARK_CLOSE), re.S)
TYPE_BLOCK = re.compile(r"\n?" + re.escape(TYPE_OPEN) + ".*?" + re.escape(TYPE_CLOSE), re.S)


def targets():
    from _app.multi import migration
    historical=set(migration(ROOT).get("artifact_paths",{}).values())
    for path in sorted(ROOT.rglob("*.html")):
        if path.relative_to(ROOT).as_posix() in historical: continue
        if set(path.relative_to(ROOT).parts) & SKIP_DIRS:
            continue
        if path.name == "index.html":
            continue                       # generated; its renderer supplies the block
        yield path


def apply(source):
    """Return (text, changed). Idempotent."""
    if 'name="artifact.brand" content="aurora"' in source or "--aurora-page-bg" in source:
        return source, False
    original = source
    source = BLOCK.sub("", source)

    # The attribute pins light and would defeat prefers-color-scheme.
    source = re.sub(r'(<html[^>]*?)\s+data-theme="light"', r"\1", source, count=1)

    source = TYPE_BLOCK.sub("", source)

    root = re.search(r":root\{.*?\}", source, re.S)
    if not root:
        return original, False
    source = source[:root.end()] + "\n" + THEME_CSS + source[root.end():]

    # Typography goes last in the sheet: it overrides the artifact's own rules
    # by order, so it must sit after them.
    close = source.rfind("</style>")
    if close != -1:
        source = source[:close].rstrip("\n") + "\n" + TYPE_CSS + "\n" + source[close:]
    return source, source != original


def main():
    check = "--check" in sys.argv
    changed, clean = [], 0
    for path in targets():
        text = path.read_text(encoding="utf-8")
        updated, differs = apply(text)
        if differs:
            changed.append(path.relative_to(ROOT))
            if not check:
                path.write_text(updated, encoding="utf-8")
        else:
            clean += 1

    verb = "would update" if check else "updated"
    for rel in changed:
        print(f"  {verb} {rel}")
    print(f"{len(changed)} {verb}, {clean} already current")
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
