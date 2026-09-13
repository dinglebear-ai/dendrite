#!/usr/bin/env python3
"""Render a superpowers plan (Markdown) into a shareable HTML artifact.

The .md is the source of truth: agents write it with superpowers:writing-plans
and tick its checkboxes while executing. This produces the human-facing artifact
from that file — same design system as every other artifact, progress visible at
a glance — so the plan can be shared with people without handing them a raw
task list.

Run:  scripts/render-plan.py plans/2026-08-27-feature.md
      scripts/render-plan.py --all
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from _app.highlight import CSS as HIGHLIGHT_CSS  # noqa: E402
from _app.highlight import highlight  # noqa: E402
PLANS = ROOT / "plans"


def esc(s):
    return html.escape(str(s), quote=True)


def inline(s):
    """Escape, then honour Markdown inline code and bold in prose fields."""
    out = esc(s)
    out = re.sub(r"`([^`]+)`", r'<span class="mono">\1</span>', out)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)


def donor():
    """Stylesheet, header, and footer from a real artifact — never re-typed."""
    best = None
    for p in sorted(ROOT.glob("*/*.html")):
        if p.name.startswith("_") or "template" in p.name or "generated" in p.read_text()[:2000]:
            continue
        src = p.read_text(encoding="utf-8")
        css = re.search(r"(@font-face.*?)\n</style>", src, re.S)
        top = re.search(r'(<header class="top">.*?</header>)', src, re.S)
        if css and top and (best is None or len(css.group(1)) > len(best[0])):
            best = (css.group(1), top.group(1))
    if best is None:
        sys.exit("no artifact to source the design system from")
    return best


FENCE = "\x00FENCE%d\x00"


def mask_code(src):
    """Replace fenced blocks with sentinels so structure parsing ignores examples.

    A plan about plans quotes "### Task" headings and "- [ ] **Step" lines as
    data; without this the renderer would count them as real tasks and steps.
    """
    blocks = []

    def take(match):
        blocks.append((match.group(2), match.group(3).rstrip()))
        return FENCE % (len(blocks) - 1)

    return re.sub(r"(`{3,})(\w*)\n(.*?)^\1`*[ \t]*$", take, src, flags=re.S | re.M), blocks


def unmask(text, blocks):
    """Sentinels back to (prose, code) for one step body."""
    code = [blocks[int(i)] for i in re.findall(r"\x00FENCE(\d+)\x00", text)]
    prose = re.sub(r"\x00FENCE\d+\x00", "", text)
    prose = re.sub(r"^\s*-{3,}\s*$", "", prose, flags=re.M)   # task separators are not prose
    return prose.strip(), code


FILE_VERBS = {"create": "new", "modify": "edit", "delete": "drop",
              "test": "test", "read": "read"}

# The TDD cycle has a shape. Colouring it makes a missing verify step visible
# at a glance instead of requiring a read.
STEP_KINDS = (
    (r"\bcommit\b", "commit"),
    (r"verify it fails|watch it fail|to verify it fails", "expect-fail"),
    (r"verify it passes|verify nothing regressed|run every test|watch it pass", "expect-pass"),
    (r"\bwrite the failing test\b|\bfailing test\b", "test"),
    (r"\bimplement|implementation\b", "implement"),
    (r"^run\b|\brun the\b|\bverify\b", "run"),
)


def step_kind(title):
    lowered = title.lower()
    for pattern, kind in STEP_KINDS:
        if re.search(pattern, lowered):
            return kind
    return "step"


def render_file(entry):
    """`Create: path/to.py` becomes a coloured verb badge plus a mono path."""
    match = re.match(r"\s*\*{0,2}(\w+)\*{0,2}\s*:\s*(.+)$", entry)
    if not match or match.group(1).lower() not in FILE_VERBS:
        return '<a class="source">' + inline(entry) + "</a>"
    verb, rest = match.group(1).lower(), match.group(2)
    path, _, note = rest.partition(" (")
    tail = ' <span class="note">(' + inline(note) + "</span>" if note else ""
    return ('<a class="source"><span class="verb ' + FILE_VERBS[verb] + '">' + esc(verb)
            + "</span>" + inline(path.strip()) + tail + "</a>")


def render_iface(entry, lang):
    """`Produces: sig` — label plain, signature highlighted as code."""
    match = re.match(r"\s*\*{0,2}(Consumes|Produces)\*{0,2}\s*:\s*(.*)$", entry, re.I)
    if not match:
        return "<div>" + inline(entry) + "</div>"
    body = re.sub(r"`([^`]+)`", lambda m: highlight(m.group(1), lang), esc_backticks(match.group(2)))
    return ('<div><span class="ilabel">' + esc(match.group(1).lower()) + "</span>"
            + body + "</div>")


def esc_backticks(text):
    """Escape everything except the backtick spans, which highlight() will escape."""
    parts = re.split(r"(`[^`]+`)", text)
    return "".join(part if part.startswith("`") else esc(part) for part in parts)


def render_prose(text):
    """Colour the outcome of a Run:/Expected: pair — PASS green, FAIL red."""
    out = inline(text)
    out = re.sub(r"\b(Run|Expected):", r'<span class="plabel">\1:</span>', out)
    out = re.sub(r"\b(PASS|OK)\b", r'<span class="pass">\1</span>', out)
    out = re.sub(r"\b(FAIL(?:ED)?)\b", r'<span class="fail">\1</span>', out)
    return out


def parse(src):
    """Pull the writing-plans structure out of the Markdown."""
    plan = {"meta": {}, "constraints": [], "files": [], "tasks": []}

    if src.startswith("---"):
        block = src.split("---", 2)[1]
        plan["meta"] = {k: v.strip().strip('"\'')
                        for k, v in re.findall(r"^artifact\.(\w+):\s*(.+)$", block, re.M)}
        src = src.split("---", 2)[2]

    h1 = re.search(r"^#\s+(.+)$", src, re.M)
    plan["title"] = h1.group(1).strip() if h1 else "Implementation Plan"
    for field in ("Goal", "Architecture", "Tech Stack"):
        m = re.search(rf"^\*\*{field}:\*\*\s*(.+)$", src, re.M)
        plan[field.lower().replace(" ", "_")] = m.group(1).strip() if m else ""

    gc = re.search(r"^## Global Constraints\s*(.*?)^(?:##|---)", src, re.S | re.M)
    if gc:
        plan["constraints"] = [l.strip("- ").strip()
                               for l in gc.group(1).splitlines() if l.strip().startswith("- ")]

    fs = re.search(r"^## File Structure\s*(.*?)^(?:###|---)", src, re.S | re.M)
    if fs:
        for row in re.findall(r"^\|\s*`?([^|`]+)`?\s*\|\s*(.+?)\s*\|$", fs.group(1), re.M):
            if "---" in row[0] or row[0].strip().lower() == "file":
                continue
            plan["files"].append((row[0].strip(), row[1].strip()))

    src, blocks = mask_code(src)
    for chunk in re.split(r"^### Task \d+:", src, flags=re.M)[1:]:
        chunk = re.split(r"^## ", chunk, flags=re.M)[0]
        task = {"name": chunk.splitlines()[0].strip(), "files": [], "interfaces": [], "steps": []}
        fb = re.search(r"\*\*Files:\*\*\s*(.*?)(?:\n\n|\*\*Interfaces)", chunk, re.S)
        if fb:
            task["files"] = [l.strip("- ").strip() for l in fb.group(1).splitlines() if l.strip().startswith("- ")]
        ib = re.search(r"\*\*Interfaces:\*\*\s*(.*?)(?:\n\n- \[|\Z)", chunk, re.S)
        if ib:
            task["interfaces"] = [l.strip("- ").strip() for l in ib.group(1).splitlines() if l.strip().startswith("- ")]

        for m in re.finditer(r"^- \[([ x])\] \*\*(.+?)\*\*\s*(.*?)(?=^- \[[ x]\]|\Z)",
                             chunk, re.S | re.M):
            prose, code = unmask(m.group(3), blocks)
            task["steps"].append({"done": m.group(1) == "x", "title": m.group(2).strip(),
                                  "prose": prose, "code": code})
        plan["tasks"].append(task)
    return plan


def render(plan, source_name):
    css, top = donor()
    m = plan["meta"]
    steps = [s for t in plan["tasks"] for s in t["steps"]]
    done = sum(1 for s in steps if s["done"])
    touched = {f.split("`")[1] if "`" in f else f
               for t in plan["tasks"] for f in t["files"]}

    top = re.sub(r'(<div class="brand">.*?)>[^<]*</span></div>',
                 r'\1>Core plan</span></div>', top, flags=re.S)
    top = re.sub(r'<div class="commit">.*?</div>',
                 f'<div class="commit">plan source <b>{esc(source_name)}</b></div>', top, flags=re.S)

    title = plan["title"].replace(" Implementation Plan", "")
    words = title.split()
    cut = max(1, round(len(words) / 2))          # balanced two-line headline
    head, tail = " ".join(words[:cut]), " ".join(words[cut:])

    langs = [lang for t in plan["tasks"] for s in t["steps"] for lang, _ in s["code"] if lang]
    main_lang = max(set(langs), key=langs.count) if langs else ""

    tasks_html = []
    for i, t in enumerate(plan["tasks"], 1):
        tdone = sum(1 for s in t["steps"] if s["done"])
        state = "complete" if tdone == len(t["steps"]) and t["steps"] else (
            "in progress" if tdone else "not started")
        cls = {"complete": "runtime", "in progress": "high", "not started": "medium"}[state]
        rows = []
        for s in t["steps"]:
            code = ""
            for lang, body in s["code"]:
                label = ' data-lang="' + esc(lang) + '"' if lang else ""
                code += '<div class="code"' + label + ">" + highlight(body, lang) + "</div>"
            flat = re.sub(r"\s+", " ", s["prose"])
            prose = f'<span>{render_prose(flat)}</span>' if s["prose"] else ""
            kind = step_kind(s["title"])
            rows.append(f'<div class="step {kind}{" done" if s["done"] else ""}">'
                        f'<b>{esc(s["title"])}</b>{prose}{code}</div>')
        links = "".join(render_file(f) for f in t["files"])
        iface = "".join(render_iface(x, main_lang) for x in t["interfaces"])
        tasks_html.append(
            f'<details class="issue" id="t{i}"{" open" if i == 1 else ""}>'
            f'<summary><span class="rank">T{i}</span><span class="title"><h3>{esc(t["name"])}</h3>'
            f'<p>{tdone} of {len(t["steps"])} steps complete · {len(t["files"])} files</p></span>'
            f'<span class="tags"><span class="tag {cls}">{state}</span><span class="chev"></span></span></summary>'
            f'<div class="detail"><div><h4>Steps</h4><div class="trace">{"".join(rows)}</div></div>'
            f'<aside><h4>Files</h4><div class="links">{links}</div>'
            + (f'<h4 style="margin-top:22px">Interfaces</h4><div class="iface">{iface}</div>' if iface else "")
            + "</aside></div></details>")

    constraints = "".join(f'<article><p>{inline(c)}</p></article>' for c in plan["constraints"])
    filerows = "".join(f'<tr><td class="mono">{esc(f)}</td><td>{inline(d)}</td></tr>'
                       for f, d in plan["files"])
    jump = "".join(f'<a class="filter" href="#t{i}">{esc(t["name"][:28])}'
                   f'<span class="count">T{i}</span></a>' for i, t in enumerate(plan["tasks"], 1))
    meta_tags = "\n".join(f'<meta name="artifact.{k}" content="{esc(v)}">'
                          for k, v in m.items())

    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unraid Core — {esc(title)}</title>
{meta_tags}
<meta name="artifact.generated" content="{esc(source_name)}">
<!-- Generated by scripts/render-plan.py from {esc(source_name)} — edit the Markdown, not this file. -->
<style>
{css}
{HIGHLIGHT_CSS}
.iface{{display:grid;gap:10px;font:500 11.5px/1.6 var(--mono);color:var(--bc)}}
.ilabel{{display:block;font:650 9px var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:3px}}
.verb{{display:inline-block;min-width:52px;margin-right:8px;font:650 9px var(--body);letter-spacing:.06em;text-transform:uppercase}}
.verb.new{{color:color-mix(in srgb,var(--ok) 66%,var(--bc))}}
.verb.edit{{color:color-mix(in srgb,var(--warn) 62%,var(--bc))}}
.verb.drop{{color:var(--err)}}
.verb.test{{color:color-mix(in srgb,var(--info) 62%,var(--bc))}}
.verb.read{{color:var(--muted)}}
.note{{color:var(--muted)}}
.plabel{{font-weight:650;color:var(--muted)}}
.pass{{color:color-mix(in srgb,var(--ok) 62%,var(--bc));font-weight:650}}
.fail{{color:var(--err);font-weight:650}}
.step.test:before{{background:var(--err)}}
.step.expect-fail:before{{background:var(--err)}}
.step.implement:before{{background:var(--p)}}
.step.expect-pass:before{{background:var(--ok)}}
.step.run:before{{background:var(--info)}}
.step.commit:before{{background:var(--b3);box-shadow:0 0 0 1px var(--muted)}}
.step.done b{{color:color-mix(in srgb,var(--ok) 62%,var(--bc))}}
.step.done:before{{background:var(--ok)}}
.step .evidence{{margin:8px 0 0}}
.fstruct{{width:100%;border-collapse:collapse;font-size:12px}}
.fstruct td{{border-bottom:1.5px solid var(--b3);padding:10px 12px 10px 0;vertical-align:top}}
.fstruct td.mono{{font:500 11.5px var(--mono);white-space:nowrap;padding-right:28px}}
.wrap{{overflow-x:auto}}
</style>
</head>
<body><div class="shell">
{top}
<main>
<section class="hero"><div><div class="eyebrow">Implementation plan / {esc(m.get("topic", "core"))}</div>
<h1>{esc(head)}<br><span>{esc(tail)}</span></h1><p>{inline(plan["goal"])}</p></div>
<aside class="verified"><h2>Plan · {esc(m.get("date", ""))}</h2><ul>
<li><span>Tasks</span><strong>{len(plan["tasks"]):02d}</strong></li>
<li><span>Steps</span><strong>{len(steps):02d}</strong></li>
<li><span>Complete</span><strong>{done} / {len(steps)}</strong></li>
<li><span>Status</span><strong>{esc(m.get("status", "draft"))}</strong></li></ul></aside></section>
<section class="stats">
<div class="stat"><div class="num">{len(plan["tasks"]):02d}</div><div class="label">Tasks</div></div>
<div class="stat"><div class="num">{done}/{len(steps)}</div><div class="label">Steps complete</div></div>
<div class="stat"><div class="num">{len(touched):02d}</div><div class="label">Files touched</div></div>
<div class="stat"><div class="num">{len(plan["constraints"]):02d}</div><div class="label">Global constraints</div></div></section>
<section class="kit"><div><strong>Architecture</strong><span>{inline(plan["architecture"])}</span></div>
<div class="kitlinks"><a href="{esc(source_name)}">SOURCE MARKDOWN</a></div></section>

<div class="layout"><aside class="rail"><h2>Tasks</h2><div class="filters">{jump}</div>
<div class="scope">Generated from the plan agents execute. Edit the Markdown; this page is rebuilt from it.<code>{esc(plan.get("tech_stack", ""))}</code></div></aside>
<section>
<div class="sectionhead"><h2>File structure</h2><p>Every file this plan creates or modifies, and what each one is responsible for.</p></div>
<div class="wrap"><table class="fstruct"><tbody>{filerows}</tbody></table></div>

<div class="sectionhead" style="margin-top:44px"><h2>Tasks</h2><p>Each task ends with an independently testable deliverable. Open one for its steps, files, and interfaces.</p></div>
<div class="issues">{"".join(tasks_html)}</div>

<section class="excluded"><div class="sectionhead"><h2>Global constraints</h2><p>Project-wide requirements. Every task inherits them.</p></div>
<div class="excluded-grid">{constraints}</div></section>
</section></div></main>
<footer><span>Rendered from <span class="mono">{esc(source_name)}</span> — the plan agents execute.</span><span class="mono">{esc(plan.get("tech_stack", ""))} · {esc(m.get("date", ""))}</span></footer>
</div>
</body></html>
"""


def main():
    import subprocess
    from _app.projects import SKILL, library_root
    targets=sorted(library_root().glob('*/plans/*.md')) if '--all' in sys.argv else [Path(a) for a in sys.argv[1:]]
    if not targets: raise SystemExit('usage: render-plan.py PATH.md | --all')
    for path in targets:
        subprocess.run([sys.executable,str(SKILL/'scripts/artifacts.py'),'render-plan',str(path)],check=True)

if __name__=='__main__':main()
