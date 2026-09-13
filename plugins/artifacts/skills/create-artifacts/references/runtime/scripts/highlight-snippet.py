#!/usr/bin/env python3
"""Emit a highlighted <div class="code"> block to paste into an authored artifact.

Reports are written by hand, so they cannot call the renderer. This produces the
markup for a genuine source snippet. Use it only for source code — observed
output belongs in a plain .evidence block, verbatim and uncoloured.

Run:  scripts/highlight-snippet.py path/to/file.ex elixir
      scripts/highlight-snippet.py - python < snippet.py
      scripts/highlight-snippet.py path/to/file.ex elixir --lines 240-268
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from _app.highlight import highlight  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        sys.exit(__doc__)
    target, lang = args[0], args[1]
    code = sys.stdin.read() if target == "-" else Path(target).read_text()

    if "--lines" in sys.argv:
        span = sys.argv[sys.argv.index("--lines") + 1]
        first, _, last = span.partition("-")
        rows = code.splitlines()
        code = "\n".join(rows[int(first) - 1:int(last or first)])

    print('<div class="code" data-lang="' + lang + '">' + highlight(code.rstrip(), lang) + "</div>")


if __name__ == "__main__":
    main()
