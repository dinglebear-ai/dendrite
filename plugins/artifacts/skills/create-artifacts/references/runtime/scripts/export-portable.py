#!/usr/bin/env python3
"""Export a shareable copy of the library with local paths made portable.

Every artifact cites sources as file:///Users/... links. Those are correct on
the machine that produced them and dead everywhere else, which defeats the
point of a rendered artifact. This writes dist/ with each link rewritten
through the "repos" map in index-meta.json:

    "repos": {
      "/Users/jmagar/workspace/core": {
        "base": "https://github.com/org/core/blob",
        "ref":  "main"
      }
    }

A mapped path becomes <base>/<ref>/<path>#L<line>, pinned to the artifact's own
artifact.target commit when it declares one, so a reader lands on the code as
it was when the claim was made.

An unmapped path is NOT left as a dead link: it degrades to plain monospace
text carrying the original path in a tooltip. A citation you cannot click is
honest; one that 404s is not.

Run:  scripts/export-portable.py [--out dist]
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
SKIP_DIRS = {".git", "_app", "_tests", "scripts", "dist", "node_modules"}
FONTS = ROOT / "_app" / "static" / "fonts"
FONT_SRC = re.compile(r'url\("file://[^"]*/([\w.-]+\.woff2)"\)')
LINK = re.compile(r'<a([^>]*?)href="file://([^"#]+)(#L(\d+))?"([^>]*)>(.*?)</a>', re.S)


def load_repos():
    meta = ROOT / "index-meta.json"
    data = json.loads(meta.read_text()) if meta.exists() else {}
    return data.get("repos", {})


def rewrite(source, repos, pinned_ref):
    """Rewrite absolute file:// citations; return (html, mapped, degraded)."""
    stats = {"mapped": 0, "degraded": 0}

    def replace(match):
        before, path, _, line, after, label = match.groups()
        for local, spec in sorted(repos.items(), key=lambda kv: -len(kv[0])):
            if path.startswith(local.rstrip("/") + "/"):
                rel = path[len(local.rstrip("/")) + 1:]
                ref = pinned_ref or spec.get("ref", "main")
                url = spec["base"].rstrip("/") + "/" + ref + "/" + rel
                if line:
                    url += "#L" + line
                stats["mapped"] += 1
                return "<a" + before + 'href="' + url + '"' + after + ">" + label + "</a>"
        stats["degraded"] += 1
        cls = "source unlinked" if "source" in (before + after) else "unlinked"
        return ('<span class="' + cls + '" title="' + path + (("#L" + line) if line else "")
                + '">' + label + "</span>")

    return LINK.sub(replace, source), stats["mapped"], stats["degraded"]


UNLINKED_CSS = """
.unlinked{color:var(--muted);text-decoration:none;cursor:help;border-bottom:1px dotted var(--b3)}
.source.unlinked{display:block;font:550 11px/1.4 var(--mono)}
"""


def main():
    import subprocess
    from _app.projects import SKILL
    return subprocess.call([sys.executable,str(SKILL/'scripts/artifacts.py'),'export',*sys.argv[1:]])

if __name__ == "__main__": raise SystemExit(main())
