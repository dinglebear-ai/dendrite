"""A persistent application shell around every artifact.

Artifacts are self-contained pages: open one directly and there is no way back,
no sense of where it sits, and no route to the next one. This wraps an artifact
in shared chrome — a sticky header, a searchable sidebar of the whole library,
breadcrumbs, related links and prev/next — while leaving the artifact's own
markup and stylesheet untouched.

Every shell class is prefixed `wb-`. Artifacts already own .shell, .top, .rail,
.card and .layout, so an unprefixed shell would collide with the content it
frames.
"""
from __future__ import annotations

import re

from .catalog import design_parts, esc

STATUS_DOT = {"accepted": "ok", "review": "warn", "draft": "muted", "superseded": "muted"}

# Drawers that hold tooling rather than reading material start closed: they are
# the longest list and the least often browsed. A reader's own choice, saved in
# localStorage, overrides this on every later visit.
COLLAPSED_BY_DEFAULT = {"scripts"}

CSS = """
/* clip rather than hidden: overflow-x:hidden on body can promote it to a scroll
   container in some engines, which breaks viewport scrolling and anything that
   depends on it. clip contains the overflow with no such side effect. Not a bug
   observed here — html is the scroller today — but the safer of the two. */
.wb-body{margin:0;background:var(--b1);color:var(--bc);font:15px/1.55 var(--body);overflow-x:clip}
.wb-body,.wb-grid,.wb-main{max-width:100%}
.wb-main>*{min-width:0}
.wb-grid{display:grid;grid-template-columns:264px minmax(0,1fr);min-height:100vh}
.wb-top{position:sticky;top:0;z-index:30;grid-column:1/-1;display:grid;grid-template-columns:264px minmax(0,1fr);align-items:center;height:56px;border-bottom:1.5px solid var(--b3);background:color-mix(in srgb,var(--b1) 94%,transparent);backdrop-filter:blur(16px)}
.wb-brand{display:flex;align-items:center;gap:11px;padding-left:22px;font-weight:800;font-size:14px;text-decoration:none;color:inherit}
.wb-brand .wb-mark{display:grid;grid-template-columns:repeat(3,5px);gap:2.5px;align-items:end;height:18px}
.wb-brand i{background:var(--p);border-radius:1px}.wb-brand i:nth-child(1){height:9px}.wb-brand i:nth-child(2){height:18px}.wb-brand i:nth-child(3){height:13px}
.wb-brand span{font-weight:450;color:var(--muted)}
.wb-bar{display:flex;align-items:center;gap:14px;padding:0 26px 0 22px;min-width:0}
.wb-crumb{display:flex;align-items:center;gap:7px;font:600 12px var(--body);color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;flex:1}
.wb-crumb a{color:var(--muted);text-decoration:none}.wb-crumb a:hover{color:var(--p)}
.wb-crumb b{color:var(--bc);font-weight:650;overflow:hidden;text-overflow:ellipsis}
.wb-crumb i{color:var(--b3);font-style:normal}
.wb-act{display:flex;gap:7px;align-items:center;flex-shrink:0}
.wb-act a{text-decoration:none;border:1.5px solid var(--b3);background:var(--b1);border-radius:4px;padding:6px 9px;font:650 10px var(--body);letter-spacing:.06em;color:var(--muted)}
.wb-act a:hover{border-color:var(--p);color:var(--p)}
.wb-chip{display:inline-flex;align-items:center;gap:6px;font:650 10px var(--body);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.wb-chip:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--ok)}
.wb-chip.warning:before{background:var(--warn)}.wb-chip.error:before{background:var(--err)}
.wb-side{position:sticky;top:56px;align-self:start;height:calc(100vh - 56px);overflow-y:auto;border-right:1.5px solid var(--b3);padding:16px 12px 40px}
.wb-search{width:100%;height:34px;border:1.5px solid var(--b3);border-radius:4px;background:var(--b1);color:var(--bc);padding:0 10px;font:500 12px var(--body);margin-bottom:14px}
.wb-search:focus{outline:2px solid color-mix(in srgb,var(--p) 40%,transparent);border-color:var(--p)}
.wb-cat{margin-top:16px}
.wb-catname{display:grid;grid-template-columns:10px minmax(0,1fr) auto;gap:7px;align-items:center;padding:6px 10px;border-radius:4px;cursor:pointer;list-style:none;font:650 10px var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.wb-catname::-webkit-details-marker{display:none}
.wb-catname:hover{color:var(--p);background:var(--b2)}
.wb-catname:focus-visible{outline:2px solid var(--p);outline-offset:2px}
.wb-catname b{font-weight:500;color:var(--b3)}
.wb-caret{width:0;height:0;border-left:4px solid currentColor;border-top:3.5px solid transparent;border-bottom:3.5px solid transparent;opacity:.55;transition:transform .12s ease}
.wb-cat[open]>.wb-catname .wb-caret{transform:rotate(90deg)}
.wb-cat[data-empty]{display:none}
.wb-tools{display:flex;justify-content:flex-end;gap:10px;padding:0 10px 8px}
.wb-tools button{border:0;background:none;cursor:pointer;padding:0;font:650 9px var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.wb-tools button:hover{color:var(--p)}
@media(prefers-reduced-motion:reduce){.wb-caret{transition:none}}
.wb-item{font:500 12.5px/1.35 var(--body);text-transform:none;letter-spacing:0;text-align:left;display:grid;grid-template-columns:9px minmax(0,1fr);gap:9px;align-items:baseline;padding:6px 10px;border-radius:4px;text-decoration:none;color:var(--muted);font-size:12.5px;line-height:1.35}
.wb-item:hover{background:var(--b2);color:var(--bc)}
.wb-item.wb-on{background:color-mix(in srgb,var(--p) 11%,transparent);color:color-mix(in srgb,var(--p) 55%,var(--bc));font-weight:600}
.wb-item:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--b3);transform:translateY(-2px)}
.wb-item[data-dot=ok]:before{background:color-mix(in srgb,var(--ok) 70%,var(--bc))}
.wb-item[data-dot=warn]:before{background:var(--warn)}
.wb-main{min-width:0}
.wb-main .shell{padding-top:0}
.wb-artifact-actions{justify-content:flex-end;flex-wrap:wrap;padding:12px 40px;border-bottom:1.5px solid var(--b3);background:var(--b1)}
.wb-empty{padding:24px 10px;color:var(--muted);font-size:12px}
.wb-outline{margin:2px 0 10px 19px;padding-left:11px;border-left:1.5px solid var(--b3)}
.wb-outhead{display:flex;justify-content:space-between;align-items:baseline;gap:8px;padding:6px 8px 4px;font:650 9px var(--body);letter-spacing:.11em;text-transform:uppercase;color:var(--muted)}
.wb-outhead button{border:0;background:none;cursor:pointer;padding:0;font:650 9px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.wb-outhead button:hover{color:var(--p)}
.wb-out{display:grid;grid-template-columns:5px minmax(0,1fr);gap:8px;align-items:baseline;padding:5px 8px;border-radius:4px;text-decoration:none;color:var(--muted);font-size:12px;line-height:1.35}
.wb-out:hover{background:var(--b2);color:var(--bc)}
.wb-out.wb-here{color:var(--bc);font-weight:600}
.wb-out:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--b3);transform:translateY(-1px)}
.wb-out[data-dot=ok]:before{background:color-mix(in srgb,var(--ok) 70%,var(--bc))}
.wb-out[data-dot=warn]:before{background:var(--warn)}
.wb-out[data-dot=err]:before{background:var(--err)}
.wb-out[data-dot=info]:before{background:var(--info)}
.wb-anchor{position:absolute;left:-22px;top:22px;text-decoration:none;color:var(--b3);font:650 13px var(--mono);opacity:0;transition:opacity .12s ease}
details.issue{position:relative}
details.issue:hover .wb-anchor,.wb-anchor:focus-visible{opacity:1}
.wb-anchor:hover{color:var(--p)}
.wb-copied{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:45;background:var(--bc);color:var(--b1);border-radius:999px;padding:8px 16px;font:600 12px var(--body);opacity:0;pointer-events:none;transition:opacity .16s ease}
.wb-copied.on{opacity:1}
.wb-skip{position:absolute;left:-9999px;top:0;z-index:50;background:var(--b1);border:1.5px solid var(--p);border-radius:4px;padding:9px 14px;font:600 12px var(--body);color:var(--bc);text-decoration:none}
.wb-skip:focus{left:12px;top:10px}
@media(prefers-reduced-motion:reduce){.wb-anchor,.wb-copied{transition:none}}
.wb-help{position:fixed;inset:0;z-index:40;display:none;place-items:center;background:color-mix(in srgb,var(--bc) 55%,transparent)}
.wb-help[open]{display:grid}
.wb-help div{background:var(--b1);border:1.5px solid var(--b3);border-radius:8px;padding:22px 26px;min-width:280px;box-shadow:0 24px 70px -30px var(--bc)}
.wb-help h4{margin:0 0 14px;font-size:14px}
.wb-help dl{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;margin:0;font-size:12.5px;color:var(--muted)}
.wb-help dt{font:600 11px var(--mono);color:var(--bc)}
.wb-hits{margin-top:14px;border-top:1.5px solid var(--b3);padding-top:12px}
.wb-hits>b{display:block;padding:0 10px 8px;font:650 9px var(--body);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.wb-hit{display:block;padding:8px 10px;border-radius:4px;text-decoration:none;color:var(--muted)}
.wb-hit:hover{background:var(--b2)}
.wb-hit strong{display:block;font:600 12px var(--body);color:var(--bc)}
.wb-hit em{display:block;font:500 11.5px/1.55 var(--body);font-style:normal;margin-top:3px;overflow-wrap:anywhere}
.wb-hit mark{background:color-mix(in srgb,var(--p) 26%,transparent);color:inherit;border-radius:2px}
.wb-hit span{float:right;font:600 10px var(--body);color:var(--b3)}
.wb-foot{display:grid;grid-template-columns:1fr 1fr;gap:14px;max-width:1440px;margin:0 auto;padding:34px 40px 70px}
.wb-foot a{display:block;border:1.5px solid var(--b3);border-radius:8px;padding:16px 18px;text-decoration:none;color:inherit}
.wb-foot a:hover{border-color:var(--p)}
.wb-foot a:hover h4{color:var(--p)}
.wb-foot span{font:650 9px var(--body);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.wb-foot h4{margin:7px 0 0;font-size:15px;letter-spacing:-.01em}
.wb-foot .wb-next{text-align:right}
.wb-rel{max-width:1440px;margin:0 auto;padding:0 40px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.wb-rel span{font:650 9px var(--body);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-right:4px}
.wb-rel a{text-decoration:none;border:1.5px solid var(--b3);border-radius:999px;padding:5px 11px;font:600 12px var(--body);color:var(--muted)}
.wb-rel a:hover{border-color:var(--p);color:var(--p)}
.wb-kbd{font:600 9px var(--body);border:1.5px solid var(--b3);border-radius:3px;padding:2px 5px;color:var(--muted)}
.wb-theme{cursor:pointer;font:650 10px var(--body);letter-spacing:.05em;border:1.5px solid var(--b3);background:var(--b1);color:var(--muted);border-radius:4px;padding:6px 9px}
.wb-theme:hover{border-color:var(--p);color:var(--p)}
.wb-burger{display:none;cursor:pointer;border:1.5px solid var(--b3);background:var(--b1);color:var(--muted);border-radius:4px;padding:6px 9px;font:650 10px var(--body);letter-spacing:.05em}
.wb-burger:hover{border-color:var(--p);color:var(--p)}
.wb-scrim{display:none}
@media(max-width:820px){
  /* The bar cannot hold four controls at phone width; keep the ones that
     change what you are looking at, drop the ones that re-open it elsewhere. */
  .wb-act a:not(.wb-chip){display:none}
  .wb-chip span{display:none}
}
@media(max-width:1000px){
  .wb-grid,.wb-top{grid-template-columns:1fr}
  .wb-burger{display:block}
  .wb-brand{padding-left:16px}
  .wb-top{display:flex;justify-content:space-between;gap:12px;padding-right:14px}
  .wb-bar{padding:0;gap:8px;flex:1;justify-content:flex-end}
  .wb-crumb{display:none}
  /* The sidebar becomes a drawer: on a phone you should reach the artifact,
     not scroll past twenty links to get to it. */
  .wb-side{position:fixed;top:56px;left:0;bottom:0;width:min(320px,86vw);z-index:25;background:var(--b1);border-right:1.5px solid var(--b3);transform:translateX(-102%);transition:transform .18s ease;height:auto}
  .wb-grid.wb-open .wb-side{transform:none;box-shadow:0 0 60px -12px var(--bc)}
  .wb-grid.wb-open .wb-scrim{display:block;position:fixed;inset:56px 0 0;background:color-mix(in srgb,var(--bc) 45%,transparent);z-index:20}
  .wb-foot{grid-template-columns:1fr;padding:28px 22px 60px}
  .wb-next{text-align:left!important}
}
@media(prefers-reduced-motion:reduce){.wb-side{transition:none}}
@media(max-width:560px){.wb-crumb{display:none}.wb-artifact-actions{justify-content:flex-start;padding:10px 16px}}
"""


SEVERITY_DOT = {"high": "err", "medium": "warn", "runtime": "ok", "proof": "ok",
                "path": "info", "plan": "warn", "report": "info"}


def _outline(body):
    """Give every finding a stable id and return the outline built from them.

    Long artifacts are the ones that need navigation most — the parity spec
    carries seventy-one findings — and a <details> that is closed is invisible
    to the browser's own find. The ids also make each finding linkable.
    """
    entries = []

    def number(match):
        opening, rest = match.group(1), match.group(2)
        title = re.search(r"<h3>(.*?)</h3>", rest, re.S)
        if not title:
            return match.group(0)
        anchor = re.search(r'id="([^"]+)"', opening)
        ident = anchor.group(1) if anchor else "f%d" % (len(entries) + 1)
        tags = re.findall(r'<span class="tag (\w+)"', rest)
        dot = next((SEVERITY_DOT[t] for t in tags if t in SEVERITY_DOT), "muted")
        entries.append({"id": ident, "dot": dot,
                        "title": re.sub(r"<[^>]+>", "", title.group(1)).strip()})
        link = ('<a class="wb-anchor" href="#' + ident
                + '" title="Link to this finding" aria-label="Link to this finding">#</a>')
        if anchor:
            return "<details" + opening + ">" + rest + link
        return "<details" + opening + ' id="' + ident + '">' + rest + link

    body = re.sub(r"<details([^>]*?)>(.*?)</summary>",
                  lambda m: number(m) + "</summary>", body, flags=re.S)
    return body, entries


FONT_SRC = re.compile(r'url\("file://[^"]*/([\w.-]+\.woff2)"\)')


def local_fonts(css, prefix="/assets/fonts/"):
    """Point @font-face at the packaged copies.

    Artifacts cite the fonts by absolute path into the Core checkout, which a
    browser refuses to load over http:// — so served pages fell back to system
    faces and lost the design system's typography entirely.
    """
    return FONT_SRC.sub(lambda m: 'url("' + prefix + m.group(1) + '")', css)


def _split(source):
    """Artifact page -> (its stylesheet, its body without the standalone chrome)."""
    styles = "\n".join(re.findall(r"<style>(.*?)</style>", source, re.S))
    body = re.search(r"<body[^>]*>(.*)</body>", source, re.S)
    body = body.group(1) if body else source
    # The shell owns the header; the artifact's own sticky bar would double it.
    # Preserve report-specific controls from that header in a non-sticky toolbar.
    header = re.search(r'<header class="top">(.*?)</header>', body, re.S)
    toolbar = ""
    if header:
        actions = re.search(r'<div class="top-actions">(.*)</div>\s*$', header.group(1), re.S)
        if actions:
            toolbar = '<div class="top-actions wb-artifact-actions">' + actions.group(1) + "</div>"
    body = re.sub(r'<header class="top">.*?</header>', "", body, flags=re.S)
    return styles, toolbar + body


def _outline_html(entries):
    if len(entries) < 2:
        return ""
    rows = "".join(
        f'<a class="wb-out" data-dot="{e["dot"]}" href="#{esc(e["id"])}">'
        f'<span>{esc(e["title"])}</span></a>' for e in entries)
    return (f'<div class="wb-outline"><div class="wb-outhead">in this artifact'
            f'<button type="button" id="wbFindings" data-open="0">expand all</button></div>'
            f'{rows}</div>')


def _sidebar(catalog, current, outline=""):
    blocks = []
    for group in catalog["groups"]:
        links = []
        for item in group["items"]:
            dot = STATUS_DOT.get(item.get("status", ""), "muted")
            on = " wb-on" if item["href"] == current else ""
            hay = " ".join([item["title"], item["href"], item.get("topic", ""),
                            item.get("status", "")]).lower()
            links.append(f'<a class="wb-item{on}" data-dot="{dot}" data-find="{esc(hay)}"'
                         f'{" aria-current=page" if on else ""}'
                         f' href="/{esc(item["href"])}"><span>{esc(item["title"])}</span></a>')
            if on and outline:
                links.append(outline)
        # Open unless the drawer is tooling; either way the saved state wins.
        start_open = "" if group["name"] in COLLAPSED_BY_DEFAULT else " open"
        blocks.append(
            f'<details class="wb-cat" data-group="{esc(group["name"])}"{start_open}>'
            f'<summary class="wb-catname"><span class="wb-caret"></span>'
            f'<span class="wb-catlabel">{esc(group["name"])}</span>'
            f'<b>{len(group["items"]):02d}</b></summary>'
            f'<div class="wb-items">{"".join(links)}</div></details>')
    return "".join(blocks)


def render_shell(catalog, item, state="clean", enriched=None):
    """Wrap one artifact in the workbench chrome.

    `enriched` is the artifact after render_artifact has added its context
    section; the shell frames that, so nothing the artifact renderer appends is
    lost by putting a shell around it.
    """
    base = ""  # Each artifact owns its palette; never borrow a neighboring project’s.
    base = local_fonts(base)
    styles, body = _split(enriched if enriched is not None else item["source"])
    styles = local_fonts(styles)
    body, entries = _outline(body)

    order = [i for g in catalog["groups"] for i in g["items"]]
    index = next((n for n, i in enumerate(order) if i["href"] == item["href"]), 0)
    previous = order[index - 1] if index > 0 else None
    following = order[index + 1] if index + 1 < len(order) else None

    category = item["href"].rsplit("/", 1)[0]
    source_md = item.get("meta", {}).get("generated")
    actions = [f'<a href="/raw/{esc(item["href"])}" title="The artifact with no shell">RAW</a>']
    if source_md:
        source_md = item.get("generated_from", category + "/" + source_md)
        actions.insert(0, f'<a href="/view/{esc(source_md)}">SOURCE</a>')
    actions.append(f'<a href="/view/{esc(item["href"])}">MARKUP</a>')

    related = "".join(f'<a href="/{esc(r["href"])}">{esc(r["title"])}</a>'
                      for r in item.get("related", [])[:5])
    related_html = (f'<div class="wb-rel"><span>related</span>{related}</div>'
                    if related else "")

    def card(entry, side):
        if not entry:
            return "<span></span>"
        label = "previous" if side == "prev" else "next"
        return (f'<a class="wb-{side}" href="/{esc(entry["href"])}"><span>{label}</span>'
                f'<h4>{esc(entry["title"])}</h4></a>')

    brand_html = '<span class="wb-mark"><i></i><i></i><i></i></span>UNRAID <span>artifacts</span>'
    if item.get("brand") == "aurora":
        from .projects import SKILL
        brand_html = (SKILL / "assets/aurora/mark.svg").read_text() + (SKILL / "assets/aurora/wordmark.html").read_text()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(item["title"])} — Project Artifacts</title>
<script>(function(){{try{{var t=localStorage.getItem("wb-theme");if(t&&t!=="auto")document.documentElement.dataset.theme=t}}catch(e){{}}}})();</script>
<style>
{base}
{styles}
{CSS}
</style>
</head>
<body class="wb-body">
<a class="wb-skip" href="#wbContent">Skip to artifact</a>
<div class="wb-copied" id="wbCopied" role="status" aria-live="polite">Link copied</div>
<div class="wb-grid">
  <header class="wb-top">
    <button class="wb-burger" id="wbBurger" type="button" aria-label="Toggle navigation" aria-expanded="false" aria-controls="wbNav">MENU</button>
    <a class="wb-brand" href="/">{brand_html}</a>
    <div class="wb-bar">
      <div class="wb-crumb"><a href="/#{esc(category)}">{esc(category)}</a><i>/</i><b>{esc(item["title"])}</b></div>
      <div class="wb-act">
        {"".join(actions)}
        <button class="wb-theme" id="wbTheme" title="Theme: auto, light, dark">AUTO</button>
        <a class="wb-chip {esc(state)}" href="/#health">{esc(state)}</a>
      </div>
    </div>
  </header>

  <div class="wb-scrim" id="wbScrim"></div>
  <aside class="wb-side" aria-label="Artifact library">
    <input class="wb-search" id="wbSearch" type="search" placeholder="Filter artifacts    /" aria-label="Filter artifacts">
    <div class="wb-tools"><button id="wbAll" type="button">expand all</button>
      <button id="wbNone" type="button">collapse all</button></div>
    <div id="wbNav">{_sidebar(catalog, item["href"], _outline_html(entries))}</div>
    <p class="wb-empty" id="wbEmpty" hidden>No artifact name matches.</p>
    <div class="wb-hits" id="wbHits" hidden><b>in content</b><div id="wbHitList"></div></div>
  </aside>

  <div class="wb-help" id="wbHelp" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts"><div>
    <h4>Keyboard</h4>
    <dl><dt>/</dt><dd>filter artifacts</dd>
      <dt>n / p</dt><dd>next / previous finding</dd>
      <dt>[ / ]</dt><dd>previous / next artifact</dd>
      <dt>e</dt><dd>expand or collapse all findings</dd>
      <dt>g</dt><dd>go to the index</dd>
      <dt>t</dt><dd>cycle theme</dd>
      <dt>?</dt><dd>this help</dd>
      <dt>Esc</dt><dd>close</dd></dl>
  </div></div>

  <main class="wb-main" id="wbContent" tabindex="-1">
    {body}
    {related_html}
    <nav class="wb-foot">{card(previous, "prev")}{card(following, "next")}</nav>
  </main>
</div>
<script>
(function(){{
  var search=document.getElementById("wbSearch"),
      nav=document.getElementById("wbNav"),
      empty=document.getElementById("wbEmpty"),
      items=[].slice.call(nav.querySelectorAll(".wb-item"));
  var groups=[].slice.call(nav.querySelectorAll(".wb-cat")), KEY="wb-open", searching=false, resting=null;

  function readOpen(){{
    try{{return JSON.parse(localStorage.getItem(KEY))||null}}catch(e){{return null}}
  }}
  function writeOpen(){{
    if(searching) return;                       // a search opens groups temporarily
    var state={{}};
    groups.forEach(function(g){{state[g.dataset.group]=g.open}});
    try{{localStorage.setItem(KEY,JSON.stringify(state))}}catch(e){{}}
  }}

  // Restore the reader's own expand state, but never hide the artifact they are on.
  var saved=readOpen();
  if(saved) groups.forEach(function(g){{
    if(g.querySelector(".wb-on")) return;
    if(g.dataset.group in saved) g.open=saved[g.dataset.group];
  }});

  groups.forEach(function(g){{g.addEventListener("toggle",writeOpen)}});

  function filter(){{
    var q=search.value.trim().toLowerCase(), shown=0;
    if(q&&!searching){{                          // remember where to return to
      searching=true;
      resting=groups.map(function(g){{return g.open}});
    }}
    items.forEach(function(a){{
      var hit=!q||a.dataset.find.indexOf(q)>-1;
      a.hidden=!hit; if(hit) shown++;
    }});
    groups.forEach(function(g,i){{
      var any=[].some.call(g.querySelectorAll(".wb-item"),function(a){{return !a.hidden}});
      if(any) g.removeAttribute("data-empty"); else g.setAttribute("data-empty","");
      if(q) g.open=any;                          // matches must be visible to be useful
      else if(resting) g.open=resting[i];
    }});
    if(!q&&searching){{searching=false;resting=null}}
    empty.hidden=shown>0;
  }}
  // Content search: titles filter instantly, content follows from /find.
  var hits=document.getElementById("wbHits"), hitList=document.getElementById("wbHitList"),
      timer=null, inflight=null;
  function escapeHtml(v){{return v.replace(/[&<>"]/g,function(c){{
    return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
  function renderHits(data){{
    if(!data.results.length){{hits.hidden=true;hitList.innerHTML="";return}}
    hitList.innerHTML=data.results.map(function(r){{
      var lines=r.lines.map(function(l){{
        return "<em>"+escapeHtml(l).replace(/\u0000/g,"<mark>").replace(/\u0001/g,"</mark>")+"</em>";
      }}).join("");
      return '<a class="wb-hit" href="/'+encodeURI(r.href)+'"><span>'+r.hits+
             "</span><strong>"+escapeHtml(r.title)+"</strong>"+lines+"</a>";
    }}).join("");
    hits.hidden=false;
  }}
  function lookup(){{
    var q=search.value.trim();
    if(q.length<2){{hits.hidden=true;hitList.innerHTML="";return}}
    if(inflight) inflight.abort&&inflight.abort();
    var controller=window.AbortController?new AbortController():null;
    inflight=controller;
    fetch("/find?q="+encodeURIComponent(q),controller?{{signal:controller.signal}}:undefined)
      .then(function(r){{return r.json()}})
      .then(function(d){{if(d.query.trim()===search.value.trim()) renderHits(d)}})
      .catch(function(){{}});
  }}
  search.addEventListener("input",function(){{
    filter();
    clearTimeout(timer); timer=setTimeout(lookup,160);
  }});

  // Drawer, for viewports where the sidebar cannot sit beside the artifact.
  var grid=document.querySelector(".wb-grid"),
      burger=document.getElementById("wbBurger"),
      scrim=document.getElementById("wbScrim");
  function drawer(open){{
    grid.classList.toggle("wb-open",open);
    burger.setAttribute("aria-expanded",open?"true":"false");
  }}
  burger.addEventListener("click",function(){{drawer(!grid.classList.contains("wb-open"))}});
  scrim.addEventListener("click",function(){{drawer(false)}});
  nav.addEventListener("click",function(e){{if(e.target.closest(".wb-item")) drawer(false)}});
  hitList.addEventListener("click",function(){{drawer(false)}});

  function setAll(open){{
    searching=false;resting=null;
    groups.forEach(function(g){{g.open=open}});
    writeOpen();
  }}
  document.getElementById("wbAll").addEventListener("click",function(){{setAll(true)}});
  document.getElementById("wbNone").addEventListener("click",function(){{setAll(false)}});

  var order=["auto","light","dark"], theme="auto", button=document.getElementById("wbTheme");
  try{{theme=localStorage.getItem("wb-theme")||"auto"}}catch(e){{}}
  function paint(){{
    if(theme==="auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme=theme;
    button.textContent=theme.toUpperCase();
  }}
  paint();
  button.addEventListener("click",function(){{
    theme=order[(order.indexOf(theme)+1)%order.length];
    try{{localStorage.setItem("wb-theme",theme)}}catch(e){{}}
    paint();
  }});
  var current=nav.querySelector(".wb-on");
  if(current) current.scrollIntoView({{block:"center"}});
  // Findings: open on deep link, step with n/p, bulk-toggle with e.
  var findings=[].slice.call(document.querySelectorAll("details.issue")),
      outline=[].slice.call(document.querySelectorAll(".wb-out")),
      bulk=document.getElementById("wbFindings"),
      help=document.getElementById("wbHelp");

  function openHash(){{
    if(!location.hash) return;
    var target=document.querySelector(location.hash);
    if(target&&target.tagName==="DETAILS"){{target.open=true;target.scrollIntoView({{block:"start"}})}}
    mark();
  }}
  function mark(){{
    var id=location.hash.slice(1);
    outline.forEach(function(a){{a.classList.toggle("wb-here",a.getAttribute("href")==="#"+id)}});
  }}
  help.addEventListener("click",function(e){{if(e.target===help) help.removeAttribute("open")}});
  window.addEventListener("hashchange",openHash);
  openHash();

  // Scroll-spy: the outline should say where you are, not where you last clicked.
  if(window.IntersectionObserver&&findings.length){{
    var visible=new Set();
    var spy=new IntersectionObserver(function(entries){{
      entries.forEach(function(entry){{
        if(entry.isIntersecting) visible.add(entry.target.id); else visible.delete(entry.target.id);
      }});
      var first=findings.filter(function(d){{return visible.has(d.id)}})[0];
      if(first) outline.forEach(function(a){{
        a.classList.toggle("wb-here",a.getAttribute("href")==="#"+first.id);
      }});
    }},{{rootMargin:"-56px 0px -70% 0px"}});
    findings.forEach(function(d){{spy.observe(d)}});
  }}

  // Anchors are real links first; the clipboard is the convenience on top.
  var copied=document.getElementById("wbCopied"), copyTimer=null;
  document.addEventListener("click",function(e){{
    var anchor=e.target.closest&&e.target.closest(".wb-anchor");
    if(!anchor||!navigator.clipboard) return;
    e.preventDefault();
    var url=location.origin+location.pathname+anchor.getAttribute("href");
    navigator.clipboard.writeText(url).then(function(){{
      location.hash=anchor.getAttribute("href");
      copied.classList.add("on");
      clearTimeout(copyTimer);
      copyTimer=setTimeout(function(){{copied.classList.remove("on")}},1400);
    }});
  }});

  if(bulk) bulk.addEventListener("click",function(){{
    var open=bulk.dataset.open!=="1";
    findings.forEach(function(d){{d.open=open}});
    bulk.dataset.open=open?"1":"0";
    bulk.textContent=open?"collapse all":"expand all";
  }});

  function step(delta){{
    if(!findings.length) return;
    var current=findings.findIndex(function(d){{return d.getBoundingClientRect().top>-4}});
    var next=Math.min(Math.max((current<0?findings.length:current)+delta,0),findings.length-1);
    var target=findings[next];
    target.open=true;
    location.hash="#"+target.id;
    target.scrollIntoView({{block:"start"}});
  }}

  document.addEventListener("keydown",function(e){{
    var typing=/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if(e.key==="/"&&!typing){{e.preventDefault();drawer(true);search.focus();search.select();return}}
    if(e.key==="Escape"){{
      if(typing){{search.value="";filter();hits.hidden=true;search.blur()}}
      help.removeAttribute("open"); drawer(false); return;
    }}
    if(typing||e.metaKey||e.ctrlKey||e.altKey) return;
    var prev=document.querySelector(".wb-prev"), next=document.querySelector(".wb-next");
    if(e.key==="["&&prev) location.href=prev.href;
    if(e.key==="]"&&next) location.href=next.href;
    if(e.key==="g") location.href="/";
    if(e.key==="t") button.click();
    if(e.key==="n") step(1);
    if(e.key==="p") step(-1);
    if(e.key==="e"&&bulk) bulk.click();
    if(e.key==="?") help.toggleAttribute("open");
  }});
}})();
</script>
</body>
</html>
"""
