"""Tokenize fenced code into span-wrapped HTML at render time.

Server-side so artifacts stay self-contained: no CDN, no runtime library, and
nothing to load when someone opens the file. Colours are derived from the
existing :root palette with color-mix, so highlighting adds classes but never
a new design token.

Deliberately scoped to *code*. Observed output in .evidence blocks stays
verbatim and uncoloured — evidence discipline outranks decoration.
"""
from __future__ import annotations

import html
import re

# token class -> what it marks
#   c comment   s string   k keyword   n number   a atom/type   f call
COMMON_NUM = r"\b(?:0[xXbBoO][0-9a-fA-F_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][-+]?\d+)?)\b"

LANGS = {
    "python": {
        "comment": r"#[^\n]*",
        "string": r"(?:[rbfu]{0,2})(?:\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')",
        "keyword": ("and as assert async await break class continue def del elif else except "
                    "finally for from global if import in is lambda nonlocal not or pass raise "
                    "return try while with yield True False None self"),
    },
    "elixir": {
        "comment": r"#[^\n]*",
        "string": r"(?:\"\"\"[\s\S]*?\"\"\"|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')",
        "keyword": ("def defp defmodule defstruct defmacro do end fn if else unless case cond "
                    "with for when alias import require use receive try rescue after catch "
                    "raise true false nil and or not in"),
        "atom": r"(?<![\w:]):[a-zA-Z_][\w?!]*|@[a-z_]\w*",
    },
    "bash": {
        "comment": r"#[^\n]*",
        "string": r"\"(?:\\.|[^\"\\])*\"|'[^']*'",
        "keyword": ("if then else elif fi for while do done case esac function return exit "
                    "set local export cd echo printf source"),
        "atom": r"\$\{?[\w@#?]+\}?",
    },
    "javascript": {
        "comment": r"//[^\n]*|/\*[\s\S]*?\*/",
        "string": r"`(?:\\.|[^`\\])*`|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'",
        "keyword": ("async await break case catch class const continue default delete do else "
                    "export extends finally for from function if import in instanceof let new "
                    "return static super switch this throw try typeof var void while yield "
                    "true false null undefined"),
    },
    "json": {"comment": r"(?!x)x", "string": r"\"(?:\\.|[^\"\\])*\"",
             "keyword": "true false null"},
    "yaml": {"comment": r"#[^\n]*", "string": r"\"(?:\\.|[^\"\\\n])*\"|'[^'\n]*'",
             "keyword": "true false null yes no"},
}
ALIASES = {"py": "python", "sh": "bash", "shell": "bash", "console": "bash", "zsh": "bash",
           "ex": "elixir", "exs": "elixir", "js": "javascript", "ts": "javascript",
           "yml": "yaml", "": None, "text": None, "output": None}


def _compile(spec):
    parts = [
        "(?P<c>" + spec["comment"] + ")",
        "(?P<s>" + spec["string"] + ")",
    ]
    if spec.get("atom"):
        parts.append("(?P<a>" + spec["atom"] + ")")
    parts.append("(?P<n>" + COMMON_NUM + ")")
    parts.append("(?P<k>\\b(?:" + "|".join(spec["keyword"].split()) + ")\\b)")
    parts.append(r"(?P<f>\b[A-Za-z_][\w.?!]*(?=\())")
    parts.append(r"(?P<t>\b[A-Z][\w.]*\b)")
    return re.compile("|".join(parts))


CACHE = {}


def highlight(code, lang):
    """Return HTML-escaped code with token spans, or plain escaped text."""
    name = ALIASES.get((lang or "").lower(), (lang or "").lower())
    spec = LANGS.get(name)
    if not spec:
        return html.escape(code)
    pattern = CACHE.setdefault(name, _compile(spec))

    out, last = [], 0
    for match in pattern.finditer(code):
        kind = match.lastgroup
        out.append(html.escape(code[last:match.start()]))
        out.append('<span class="' + kind + '">' + html.escape(match.group()) + "</span>")
        last = match.end()
    out.append(html.escape(code[last:]))
    return "".join(out)


CSS = """.code{background:var(--b2);border:1.5px solid var(--b3);border-radius:8px;padding:15px 16px;font:500 11px/1.6 var(--mono);white-space:pre;overflow-x:auto;margin:8px 0 0;position:relative}
.code .c{color:var(--muted);font-style:italic}
.code .s{color:color-mix(in srgb,var(--ok) 74%,var(--bc))}
.code .k{color:color-mix(in srgb,var(--p) 76%,var(--bc));font-weight:650}
.code .n{color:color-mix(in srgb,var(--info) 68%,var(--bc))}
.code .a{color:color-mix(in srgb,var(--info) 58%,var(--bc))}
.code .t{color:color-mix(in srgb,var(--info) 52%,var(--bc));font-weight:600}
.code .f{color:var(--bc);font-weight:600}
.code[data-lang]:before{content:attr(data-lang);position:absolute;top:0;right:0;padding:4px 8px;font:650 9px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);background:var(--b3);border-radius:0 6px 0 6px}
"""
