"""Full-text search across artifact content.

The sidebar filter matches titles, which answers "where is the parity spec?" but
not "which artifact discussed symlink extraction?" — the question you actually
have with twenty dense artifacts. This searches the rendered text of every
artifact and returns the matching lines, so the answer arrives with its context.

Served at /find rather than /api/search on purpose: Authelia's global rules
bypass auth for /api/* on every *.tootie.tv host, and the proxy therefore locks
/api/ to trusted source addresses. A search under /api would be unreachable for
an authenticated reader off the tailnet.
"""
from __future__ import annotations

import re

TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
WHITESPACE = re.compile(r"[ \t]+")
SNIPPET = 150


def plain_text(source):
    """Artifact markup to readable text, one line per block."""
    text = TAGS.sub("\n", source)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    text = text.replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    lines = (WHITESPACE.sub(" ", line).strip() for line in text.splitlines())
    return [line for line in lines if len(line) > 2]


def _mark(line, needle):
    out, low, target = [], line.lower(), needle.lower()
    at = 0
    while True:
        hit = low.find(target, at)
        if hit < 0:
            out.append(line[at:])
            return "".join(out)
        out.append(line[at:hit])
        out.append("\x00" + line[hit:hit + len(target)] + "\x01")
        at = hit + len(target)


def search(catalog, query, limit=40, per_artifact=3):
    """Return [{href, title, category, hits, lines}] ordered by hit count."""
    query = (query or "").strip()
    if len(query) < 2:
        return []

    results = []
    for item in catalog["items"]:
        source = item.get("source")
        body = plain_text(source) if source else [item.get("blurb", "")]
        matches = [line for line in body if query.lower() in line.lower()]
        if not matches:
            continue
        seen, lines = set(), []
        for line in matches:
            trimmed = line[:SNIPPET] + ("…" if len(line) > SNIPPET else "")
            if trimmed in seen:
                continue                      # repeated boilerplate is not a second hit
            seen.add(trimmed)
            lines.append(_mark(trimmed, query))
            if len(lines) >= per_artifact:
                break
        results.append({
            "href": item["href"], "title": item["title"],
            "category": item["href"].split("/")[0],
            "hits": len(matches), "lines": lines,
        })

    results.sort(key=lambda r: (-r["hits"], r["title"]))
    return results[:limit]
