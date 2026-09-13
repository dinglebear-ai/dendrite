"""Restrict the monospace face to code, and nothing else.

Source Code Pro was carrying most of the interface: stat numbers, eyebrows,
tags, counts, rail headings, citation links. Monospace earns its place where
character alignment means something — a snippet, a command, its output — and
costs legibility everywhere else.

This is an override block appended after the artifact's own rules rather than a
rewrite of them: same selectors, later in the sheet, so it wins without touching
a stylesheet that eighteen artifacts share byte for byte.

Kept monospace: .evidence, .code, pre, code, .mono, .iface, .fstruct td.mono
and the highlighter's token spans — every one a snippet or a path inside prose.
"""

MARK_OPEN = "/* type:begin */"
MARK_CLOSE = "/* type:end */"

# Interface chrome that had no reason to be monospace.
BODY_SELECTORS = (
    ".eyebrow", ".commit", ".num", ".verified ul", ".verified li", ".tag",
    ".rank", ".count", ".rail h2", ".detail h4", ".kit a", ".source",
    ".facts", ".label", ".step b", ".limit", ".fix", ".scope",
    ".sectionhead h2", ".filter", ".tmpl", ".relations", ".ilabel", ".plabel",
    ".verb", ".gmeta", ".gsum", ".groupbar",
)

CSS = f"""{MARK_OPEN}
{",".join(BODY_SELECTORS)}{{font-family:var(--body)}}
.num{{letter-spacing:-.03em}}
.eyebrow,.tag,.rank,.count,.rail h2,.detail h4,.kit a,.ilabel,.verb{{letter-spacing:.06em}}
.source{{font-size:12px;letter-spacing:0}}
.verified ul,.facts{{font-size:12px;letter-spacing:0}}
.commit{{letter-spacing:0}}
/* Snippets, paths and identifiers stay monospace — alignment carries meaning. */
.evidence,.code,.mono,.iface,pre,code,kbd,samp,.fstruct td.mono,.scope code{{font-family:var(--mono)}}
{MARK_CLOSE}"""
