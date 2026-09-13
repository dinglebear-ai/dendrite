"""HTML renderers for the catalog, artifacts, and source workbench."""
import html, json, re, subprocess
from pathlib import Path
from .catalog import TAGS, design_parts, esc

CSS = """
[hidden]{display:none!important}html,body{max-width:100%;overflow-x:hidden}.layout>*{min-width:0}
.cards{display:grid;gap:14px}.card{border:1.5px solid var(--b3);border-radius:8px;padding:22px;display:grid;grid-template-columns:42px minmax(0,1fr) 280px;gap:16px;text-decoration:none}.card:hover,.card:focus-visible{border-color:var(--p);outline:0}.card h3{font-size:18px;margin:0}.card p{font-size:12px;color:var(--muted);margin:6px 0}.rank{font:650 11px var(--mono);color:var(--muted)}.facts{display:grid;gap:7px;font:500 11px var(--mono);border-left:3px solid var(--b3);padding-left:16px}.facts div{display:flex;justify-content:space-between;gap:12px}.group+.group{margin-top:48px;padding-top:32px;border-top:1.5px solid var(--b3)}.sectionhead h2{font:650 22px var(--mono)}.sectionhead h2:before{content:"/";color:var(--p)}.tmpl{display:block;color:var(--p);font:600 10px var(--mono);text-decoration:none}.rail .filter{text-decoration:none;font:600 13px var(--mono)}
.stats{grid-template-columns:repeat(auto-fit,minmax(145px,1fr))}.toolbar{display:grid;grid-template-columns:minmax(240px,1fr) repeat(3,minmax(120px,180px));gap:10px;padding:18px 0;border-bottom:1.5px solid var(--b3)}.toolbar input,.toolbar select{height:42px;border:1.5px solid var(--b3);border-radius:4px;background:var(--b1);padding:0 12px;font:500 12px var(--body)}.toolbar input:focus,.toolbar select:focus{outline:2px solid color-mix(in srgb,var(--p) 40%,transparent);border-color:var(--p)}.resultCount{font:500 11px var(--mono);color:var(--muted);padding:0 0 14px}.health{margin-top:24px;border:1.5px solid var(--b3);border-left:3px solid var(--ok);border-radius:8px;padding:18px 20px}.health.errors{border-left-color:var(--err)}.health.warnings{border-left-color:var(--warn)}.healthhead{display:flex;justify-content:space-between;gap:20px}.health h2{font-size:14px;margin:0}.health ul{list-style:none;margin:14px 0 0;padding:0;display:grid;gap:8px;font:500 11px var(--mono)}.health li{display:grid;grid-template-columns:90px 180px minmax(0,1fr);gap:12px}.health li span{color:var(--muted)}.health a{overflow-wrap:anywhere;color:inherit}.health code{font-size:10px}.error strong{color:var(--err)}.relations{margin-top:12px;font:500 10px var(--mono);color:var(--muted)}.relations a{color:var(--info);margin-right:10px}.dirty{color:var(--warn)}.kit{flex-wrap:wrap}.emptySearch{display:none;color:var(--muted);padding:40px 0}.changeNotice{position:fixed;right:24px;bottom:24px;z-index:20;background:var(--b1);border:1.5px solid var(--p);border-radius:8px;padding:14px 16px;box-shadow:0 18px 48px -24px var(--bc)}.changeNotice button{margin-left:12px;border:0;background:var(--p);color:var(--pc);padding:7px;border-radius:4px}
.context{margin:48px 0 0;padding:28px 0;border-top:1.5px solid var(--b3);border-bottom:1.5px solid var(--b3)}.context h2{font-size:22px}.contextGrid{display:grid;grid-template-columns:1fr 1fr;gap:28px}.context h3{font:650 11px var(--mono);text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}.context ul{padding-left:18px}.context a{overflow-wrap:anywhere}.context .empty{color:var(--muted);font-size:13px}
.viewerTop{position:sticky;top:0;z-index:3;background:var(--b1);border-bottom:1.5px solid var(--b3);padding:12px 28px;display:flex;gap:16px;justify-content:space-between;align-items:center}.viewerTop nav{display:flex;gap:8px}.viewerTop a,.viewerTop button{text-decoration:none;border:1.5px solid var(--b3);background:var(--b1);padding:7px 9px;border-radius:4px;font:600 11px var(--mono)}.viewerTop code{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.viewer{max-width:1440px;margin:auto;padding:26px}.code{border-collapse:collapse;width:100%;font:500 12px/1.55 var(--mono)}.code th{width:58px;text-align:right;vertical-align:top;padding-right:14px;color:var(--muted);font-weight:400}.code td{white-space:pre}.wrap .code td{white-space:pre-wrap;overflow-wrap:anywhere}.kw{color:var(--info);font-weight:650}.str{color:var(--ok)}.comment{color:var(--muted)}.markdown{max-width:820px;margin:auto}.markdown h1{font-size:42px}.markdown h2{margin-top:42px;border-top:1.5px solid var(--b3);padding-top:24px}pre{background:var(--b2);padding:18px;border:1.5px solid var(--b3);border-radius:8px;overflow:auto}.diff .add{background:color-mix(in srgb,var(--ok) 12%,transparent)}.diff .del{background:color-mix(in srgb,var(--err) 10%,transparent)}.card h3 a{color:inherit;text-decoration:none}.card:focus-within{border-color:var(--p)}.card h3 a:focus-visible{outline:2px solid var(--p);outline-offset:3px}
@media(max-width:900px){.card{grid-template-columns:34px minmax(0,1fr)}.facts{grid-column:2}.toolbar{grid-template-columns:1fr 1fr}.contextGrid{grid-template-columns:1fr}}
@media(max-width:560px){.card{grid-template-columns:1fr}.facts{grid-column:auto}.health li{display:block}.health li>*{display:block;margin:3px 0}.healthhead{display:block}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.toolbar{grid-template-columns:1fr}.viewerTop{align-items:flex-start;flex-direction:column}.viewer{padding:16px}.code th{width:38px}.contextGrid{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

# Rules for the context block render_artifact appends, carved out of the index
# stylesheet so artifact pages keep their own design.
CONTEXT_CSS = "".join(re.findall(r"\.(?:context|relations)[^{,]*\{[^}]*\}", CSS))


def _issues_for(catalog, href):
    return [i for i in catalog["issues"] if i["where"] == href]

def render_index(catalog, live=False):
    base, top, footer = design_parts(catalog)
    groups, items, issues = catalog["groups"], catalog["items"], catalog["issues"]
    errors = sum(i["severity"] == "error" for i in issues); warnings = len(issues) - errors
    state = "errors" if errors else ("warnings" if warnings else "clean")
    topics = sorted({i["topic"] for i in items}); statuses = sorted({i["status"] for i in items})
    stats = "".join(f'<div class="stat"><div class="num">{len(g["items"]):02d}</div><div class="label">{esc(g["name"])}</div></div>' for g in groups)
    sections=[]; number=0
    for group in groups:
        cards=[]
        for item in group["items"]:
            number += 1
            facts="".join(f'<div><span>{esc(k)}</span><strong>{esc(v)}</strong></div>' for k,v in item["facts"])
            href=item["href"] if item["kind"]=="html" or not live else "/view/"+item["href"]
            related="".join(f'<a href="/{esc(x["href"])}">{esc(x["title"])}</a>' for x in item["related"][:3])
            search=" ".join([item["title"],item["blurb"],item["href"],group["name"],item["topic"],item["status"]]+[r["title"] for r in item["related"]]).lower()
            own_issues=_issues_for(catalog,item["href"])
            health="error" if any(i["severity"]=="error" for i in own_issues) else ("warning" if own_issues else "clean")
            dirty_class="dirty" if item["dirty"] else ""; date="modified" if item["dirty"] else esc(item["date"])
            relations_html='<div class="relations">Related · '+related+'</div>' if related else ""
            facts_html='<span class="facts">'+facts+'</span>' if facts else ""
            cards.append(f'<article class="card" data-search="{esc(search)}" data-category="{group["name"]}" data-topic="{esc(item["topic"])}" data-status="{esc(item["status"])}" data-health="{health}"><span class="rank">{number:02d}<br><span class="{dirty_class}">{date}</span></span><span><h3><a href="{esc(href)}">{esc(item["title"])}</a></h3><p>{esc(item["blurb"])}</p><span class="tags"><span class="tag {TAGS.get(group["name"],"report")}">{esc(item["status"])}</span><span class="tag file">{esc(item["topic"])}</span></span>{relations_html}</span>{facts_html}</article>')
        template=f'<a class="tmpl" href="{esc(group["template"])}">start from {esc(Path(group["template"]).name)}</a>' if group["template"] else ""
        sections.append(f'<section class="group" id="{group["name"]}"><div class="sectionhead"><h2>{group["name"]}</h2><p>{esc(group["blurb"])}{template}</p></div><div class="cards">{"".join(cards)}</div></section>')
    rows=[]
    for i in issues:
        href=("/view/"+i["where"]+(f'#L{i["line"]}' if i.get("line") else "")) if live and (catalog["root"]/i["where"]).is_file() else i["where"]
        repair='<small> · '+esc(i["repair"])+"</small>" if i.get("repair") else ""
        rows.append(f'<li class="{i["severity"]}" data-severity="{i["severity"]}"><code>{esc(i.get("rule","CHECK"))}</code><span>{esc(i["where"])}</span><strong><a href="{esc(href)}">{esc(i["message"])}</a>{repair}</strong></li>')
    live_links='<a href="/api/artifacts">LIVE JSON</a><a href="/api/status">STATUS</a>' if live else '<span>LIVE ENDPOINTS REQUIRE APP.PY</span>'
    watch='const events=new EventSource("/events");events.onmessage=e=>{if(JSON.parse(e.data).signature!=='+json.dumps(catalog["signature"])+')document.querySelector("#changeNotice").hidden=false};' if live else ""
    options=lambda values: "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in values)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project Artifact Library</title><link rel="icon" href="/assets/favicon.svg"><style>{base}{CSS}</style></head><body><a class="hidden" href="#catalog">Skip to artifacts</a><div class="shell">{top}<main><section class="hero"><div><div class="eyebrow">Project Work / Artifact Library</div><h1>{len(items)} artifacts.<br><span>Connected evidence.</span></h1><p>Search the complete review record, follow related work across artifact types, and inspect every consulted source.</p></div><aside class="verified"><h2>Package · {catalog["generated_at"]:%b %-d, %Y}</h2><ul><li><span>Filed artifacts</span><strong>{len(items):02d}</strong></li><li><span>Topics</span><strong>{len(topics):02d}</strong></li><li><span>References</span><strong>{sum(len(i["references"]) for i in items):02d}</strong></li><li><span>Package health</span><strong>{state}</strong></li></ul></aside></section><section class="stats">{stats}</section><section class="kit"><div><strong>{"Live discovery" if live else "Static export"}</strong><span>{"Filesystem events update the cached catalog." if live else "Portable snapshot; live viewers require scripts/app.py."}</span></div><div class="kitlinks">{live_links}</div></section><section class="health {state}" aria-live="polite"><div class="healthhead"><h2>Package status</h2><span>{errors} errors · {warnings} warnings</span></div>{f'<ul>{"".join(rows)}</ul>' if issues else '<p>All artifact checks clean.</p>'}</section><div class="toolbar" role="search"><input id="search" type="search" aria-label="Search artifacts" placeholder="Search artifacts, references, topics…"><select id="category" aria-label="Filter category"><option value="">All categories</option>{options(g["name"] for g in groups)}</select><select id="topic" aria-label="Filter topic"><option value="">All topics</option>{options(topics)}</select><select id="health" aria-label="Filter health"><option value="">All health states</option><option>clean</option><option>warning</option><option>error</option></select></div><div class="resultCount" id="searchCount" aria-live="polite">{len(items)} artifacts</div><div class="layout" id="catalog"><aside class="rail"><h2>Jump to</h2><div class="filters">{"".join(f'<a class="filter" href="#{g["name"]}">{g["name"]}<span>{len(g["items"]):02d}</span></a>' for g in groups)}</div></aside><div>{"".join(sections)}<p class="emptySearch" id="emptySearch">No artifacts match those filters.</p></div></div></main>{footer}</div><div class="changeNotice" id="changeNotice" role="status" hidden>Artifacts changed on disk.<button onclick="location.reload()">Refresh</button></div><script>const cards=[...document.querySelectorAll(".card")],groups=[...document.querySelectorAll(".group")],q=document.querySelector("#search"),category=document.querySelector("#category"),topic=document.querySelector("#topic"),health=document.querySelector("#health"),count=document.querySelector("#searchCount"),empty=document.querySelector("#emptySearch");const params=new URLSearchParams(location.search);for(const el of [q,category,topic,health])el.value=params.get(el.id)||"";function filter(){{let n=0;cards.forEach(c=>{{const show=(!q.value||c.dataset.search.includes(q.value.toLowerCase()))&&(!category.value||c.dataset.category===category.value)&&(!topic.value||c.dataset.topic===topic.value)&&(!health.value||c.dataset.health===health.value);c.hidden=!show;n+=show}});groups.forEach(g=>g.hidden=![...g.querySelectorAll(".card")].some(c=>!c.hidden));count.textContent=n+" artifact"+(n===1?"":"s");empty.style.display=n?"none":"block";const p=new URLSearchParams;for(const e of [q,category,topic,health])if(e.value)p.set(e.id,e.value);history.replaceState(null,"",location.pathname+(p.size?"?"+p:""))}}for(const e of [q,category,topic,health])e.addEventListener(e===q?"input":"change",filter);filter();{watch}</script></body></html>'''

def highlight(line, suffix):
    value=html.escape(line)
    if suffix in (".py",".sh",".ex",".exs",".js",".css",".yml",".yaml"):
        value=re.sub(r'(&quot;.*?&quot;|&#x27;.*?&#x27;)',r'<span class="str">\1</span>',value)
        value=re.sub(r'(^|\s)(#.*$|//.*$)',r'\1<span class="comment">\2</span>',value)
        value=re.sub(r"\b(def|defp|defmodule|do|end|if|else|case|when|fn|import|from|class|return|const|let|function|async|await|set|fi|then)\b",r'<span class="kw">\1</span>',value)
    return value or " "

def markdown(source):
    out=[]; code=[]; inside=False
    for raw in source.splitlines():
        if raw.startswith("```"):
            if inside: out.append("<pre><code>"+html.escape("\n".join(code))+"</code></pre>"); code=[]
            inside=not inside
        elif inside: code.append(raw)
        elif m:=re.match(r"^(#{1,6})\s+(.*)",raw): out.append(f'<h{len(m[1])}>{html.escape(m[2])}</h{len(m[1])}>')
        elif raw.startswith(("- ","* ")): out.append("<p>• "+html.escape(raw[2:])+"</p>")
        elif raw.strip(): out.append("<p>"+html.escape(raw)+"</p>")
    return "".join(out)

def _rows(source, suffix, diff=False):
    rows=[]
    for n,line in enumerate(source.splitlines(),1):
        cls="add" if diff and line.startswith("+") and not line.startswith("+++") else ("del" if diff and line.startswith("-") and not line.startswith("---") else "")
        rows.append(f'<tr class="{cls}" id="L{n}"><th><a href="#L{n}">{n}</a></th><td><code>{highlight(line,suffix)}</code></td></tr>')
    return '<table class="code">'+"".join(rows)+"</table>"

def render_viewer(root, rel, catalog, mode="rendered"):
    target=(root/rel).resolve()
    if root.resolve() not in target.parents or not target.is_file(): raise FileNotFoundError(rel)
    allowed={i["href"] for i in catalog["items"]} | {i["generated_from"] for i in catalog["items"] if i.get("generated_from")}
    if catalog.get("multi_project") and rel not in allowed: raise FileNotFoundError(rel)
    source=target.read_text(errors="replace"); base,_,_=design_parts(catalog)
    if mode=="diff":
        result=subprocess.run(["git","diff","--",rel],cwd=root,text=True,capture_output=True,check=False)
        body='<div class="diff">'+_rows(result.stdout or "No working-tree diff.",target.suffix,True)+"</div>"
    elif target.suffix==".md" and mode=="rendered": body='<article class="markdown">'+markdown(source)+"</article>"
    else: body=_rows(source,target.suffix)
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(target.name)} — Artifact Viewer</title><link rel="icon" href="/assets/favicon.svg"><style>{base}{CSS}</style></head><body><header class="viewerTop"><a href="/">← Library</a><code>{esc(rel)}</code><nav><a href="?mode=rendered">Rendered</a><a href="?mode=source">Source</a><a href="?mode=diff">Diff</a><button id="wrap">Wrap</button><button id="copy">Copy</button><a href="/raw/{esc(rel)}" download>Download</a></nav></header><main class="viewer">{body}</main><script>document.querySelector("#wrap").onclick=()=>document.body.classList.toggle("wrap");document.querySelector("#copy").onclick=async e=>{{await navigator.clipboard.writeText({json.dumps(source).replace("<", chr(92)+"u003c")});e.currentTarget.textContent="Copied"}}</script></body></html>'''

def render_artifact(source, item):
    related="".join(f'<li><a href="/{esc(x["href"])}">{esc(x["title"])}</a> <span class="tag">{esc(x["category"])}</span></li>' for x in item["related"])
    refs="".join('<li><a href="'+esc(x["href"])+"\">"+esc(x["label"])+"</a>"+(f' <span class="mono">artifact line {x["line"]}</span>' if x.get("line") else "")+"</li>" for x in item["references"])
    section=f'<section class="context"><h2>Relevant docs &amp; references</h2><div class="contextGrid"><div><h3>Related artifacts</h3>{f"<ul>{related}</ul>" if related else "<p class=empty>No related artifacts are currently indexed.</p>"}</div><div><h3>Documentation, research &amp; repository references</h3>{f"<ul>{refs}</ul>" if refs else "<p class=empty>No consulted references were recorded.</p>"}</div></div></section>'
    # Inject only what this appended section needs. The full index stylesheet
    # also defines .card, .sectionhead, .stats, .kit, .rail and .filter, which
    # artifacts own — injecting all of it restyled every artifact page.
    style=f'<style>{CONTEXT_CSS}</style>'
    return source.replace("</head>",style+"</head>").replace("</main>",section+"</main>",1)
