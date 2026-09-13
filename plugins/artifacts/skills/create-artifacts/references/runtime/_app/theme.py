"""The dark palette, derived from the existing Unraid light tokens.

Every value keeps its light counterpart's hue and chroma and moves only
lightness, so the artifacts read as the same design system after dark. The
brand orange (--p) is unchanged: it is the identity, and it already carries
enough contrast on a dark ground. Accent colours are lifted in lightness
because a 58%-lightness red that reads on white does not read on near-black.

Three blocks, in this order, so all three states work:
  :root                       light, the default
  prefers-color-scheme: dark  system preference, unless a theme is pinned
  [data-theme="dark"]         an explicit choice, which must win either way

Artifacts therefore carry no data-theme attribute; the app shell sets one when
a reader picks a side.
"""

MARK_OPEN = "/* dark:begin */"
MARK_CLOSE = "/* dark:end */"

DARK_TOKENS = (
    "--b1:oklch(19% .006 285.885);"
    "--b2:oklch(23% .006 285.885);"
    "--b3:oklch(31% .008 286.32);"
    "--bc:oklch(93% .002 286.375);"
    "--p:oklch(70% .213 47.604);"
    "--pc:oklch(19% .006 285.885);"
    "--info:oklch(71% .16 259.815);"
    "--ok:oklch(76% .13 182.503);"
    "--warn:oklch(77% .15 58.318);"
    "--err:oklch(69% .2 17.585);"
    "--muted:color-mix(in srgb,var(--bc) 58%,transparent)"
)

CSS = f"""{MARK_OPEN}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]){{{DARK_TOKENS}}}}}
:root[data-theme=dark]{{{DARK_TOKENS}}}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]) .chev{{background:var(--b3)}}}}
:root[data-theme=dark] .chev{{background:var(--b3)}}
@media(prefers-color-scheme:dark){{:root:not([data-theme=light]) .issue:hover,:root:not([data-theme=light]) .card:hover{{box-shadow:none;border-color:color-mix(in srgb,var(--bc) 26%,var(--b3))}}}}
:root[data-theme=dark] .issue:hover,:root[data-theme=dark] .card:hover{{box-shadow:none;border-color:color-mix(in srgb,var(--bc) 26%,var(--b3))}}
{MARK_CLOSE}"""
