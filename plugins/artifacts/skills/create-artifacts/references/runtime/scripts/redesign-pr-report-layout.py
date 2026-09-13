#!/usr/bin/env python3
"""Apply the reviewer-route information architecture to PR report HTML files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = json.loads((ROOT / "pr-reports/schema/sections.json").read_text())
STAGE_DESCRIPTIONS = {
    "orient": "Understand the problem, identity, and lifecycle.",
    "change": "Audit decisions, files, dependencies, patterns, and docs.",
    "prove": "Challenge verification, coverage, evidence, and cleanup.",
    "review": "Close concerns and preserve independent challenge.",
    "operate": "Inspect provenance, friction, residual risk, and next work.",
    "handoff": "Package sources, learnings, disclosure, history, and artifact QA.",
}
STAGES = [(stage["id"], stage["label"], STAGE_DESCRIPTIONS[stage["id"]], stage["sections"])
          for stage in REGISTRY["stages"]]

CSS = r"""
/* pr-review-route:begin */
.rail{max-height:calc(100vh - 96px);overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-right:8px}
html,body{max-width:100%;overflow-x:hidden}.shell{width:100%;min-width:0}.hero{padding-top:58px;grid-template-columns:minmax(0,1.4fr) minmax(300px,.6fr);align-items:start}.hero>*,.verified li>*{min-width:0}.hero h1{max-width:980px;overflow-wrap:anywhere;word-break:break-word}.hero p,.verified strong{overflow-wrap:anywhere;word-break:break-word}.verified{margin-top:4px;background:var(--b2);border:1.5px solid var(--b3);border-left:4px solid var(--ok);border-radius:8px;padding:20px 22px}.stats{background:var(--b1)}
.layout{grid-template-columns:260px minmax(0,1fr);gap:54px;padding-top:42px}.rail{top:78px}.rail-kicker{font:650 10px/1 var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--p);margin-bottom:12px}.route{display:grid;position:relative;margin:0 0 24px}.route:before{content:"";position:absolute;left:14px;top:16px;bottom:16px;width:1.5px;background:var(--b3)}.route a{position:relative;display:grid;grid-template-columns:30px 1fr;gap:10px;align-items:center;padding:8px 8px 8px 0;text-decoration:none;border-radius:6px;color:var(--muted)}.route a:hover{background:var(--b2);color:var(--bc)}.route b{position:relative;display:grid;place-items:center;width:29px;height:29px;border:1.5px solid var(--b3);border-radius:50%;background:var(--b1);font:700 10px var(--mono);color:var(--bc)}.route span{font-size:12px;font-weight:650}.rail .filters{padding-top:18px;border-top:1.5px solid var(--b3)}.rail .scope{margin-top:22px}.issues{gap:12px}.phasehead{scroll-margin-top:92px;display:grid;grid-template-columns:42px 1fr auto;gap:16px;align-items:end;padding:40px 4px 12px;margin-top:10px;border-bottom:1.5px solid var(--b3)}.phasehead:first-child{padding-top:0}.phase-index{font:700 11px var(--mono);color:var(--p)}.phasehead h3{font-size:22px;line-height:1;letter-spacing:-.03em;margin:0}.phasehead p{font-size:11px;color:var(--muted);margin:0;max-width:360px;text-align:right}.issue{scroll-margin-top:90px}.issue[open]{border-color:color-mix(in srgb,var(--p) 25%,var(--b3))}.issue[open] summary{background:color-mix(in srgb,var(--p) 4%,var(--b1))}.excluded{margin-top:64px}.sectionhead h2{font-size:32px}.sectionhead p{max-width:520px}
.detail>*,.detail.full>div{min-width:0;max-width:100%}.detail.full{grid-template-columns:minmax(0,1fr)}.ledger caption{display:block;width:100%;box-sizing:border-box;overflow-wrap:anywhere}.ledger th,.ledger td{overflow-wrap:anywhere}.detail:not(.full) .ledger tbody{min-width:0}.action-needed,.fix,.limit,.evidence{max-width:100%;box-sizing:border-box;overflow-wrap:anywhere}
.top-actions{display:flex;gap:8px}.mode-button,.copy-link,.sort-button{border:1.5px solid var(--b3);background:var(--b1);color:var(--bc);border-radius:5px;padding:7px 9px;font:650 10px var(--body);cursor:pointer}.mode-button:hover,.copy-link:hover,.sort-button:hover{border-color:var(--p);color:var(--p)}.status-summary{display:inline-block;margin-top:18px;border-left:3px solid var(--warn);padding:3px 0 3px 12px;color:var(--muted);font-size:13px}.status-ribbon{display:flex;gap:8px;flex-wrap:wrap;padding:16px 0;border-bottom:1.5px solid var(--b3)}.status-ribbon span{border:1.5px solid var(--b3);border-radius:999px;padding:6px 9px;font:700 10px var(--body);letter-spacing:.04em;text-transform:uppercase}.status-ribbon .posture{border-color:color-mix(in srgb,var(--warn) 45%,var(--b3));color:color-mix(in srgb,var(--warn) 70%,var(--bc))}.freshness{display:none;margin:18px 0 0;padding:13px 16px;border:1.5px solid color-mix(in srgb,var(--warn) 55%,var(--b3));border-left:4px solid var(--warn);border-radius:8px;background:color-mix(in srgb,var(--warn) 7%,transparent);font-size:12px}.freshness.show{display:block}.control-deck{display:grid;grid-template-columns:1.1fr .9fr;gap:14px;padding:24px 0;border-bottom:1.5px solid var(--b3)}.deck-card{border:1.5px solid var(--b3);border-radius:8px;padding:18px;background:var(--b1)}.deck-card h2{font-size:16px;margin:0 0 5px}.deck-card>p{font-size:11px;color:var(--muted);margin:0 0 14px}.diff-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.diff-item{padding:10px;border:1.5px solid var(--b3);border-radius:6px}.diff-item b{display:block;font:700 21px var(--mono)}.diff-item span{font-size:10px;color:var(--muted)}.delta-list{display:grid;gap:7px}.delta-item{display:flex;justify-content:space-between;gap:12px;font-size:11px;padding-bottom:7px;border-bottom:1px solid var(--b3)}.delta-item:last-child{border:0;padding:0}.delta-item b{font-family:var(--mono)}.stage-state{display:block!important;margin-top:3px;font:600 9px var(--mono)!important;color:var(--muted)}.state-badge{border:1.5px solid var(--b3);border-radius:999px;padding:5px 8px;font:700 9px/1 var(--mono);white-space:nowrap}.state-PASS{color:var(--ok)}.state-FAIL,.state-BLOCKED{color:var(--err)}.state-STALE,.state-NOT-RUN,.state-UNKNOWN{color:var(--warn)}.state-NOT-APPLICABLE{color:var(--muted)}.summary-tools{display:flex;gap:6px;align-items:center}.copy-link{padding:4px 7px}.action-needed{margin:12px 0 0;padding:12px 14px;border-left:3px solid var(--warn);background:var(--b2);font-size:11px}.action-needed b{display:block}.evidence-uses{display:block;margin-top:7px;color:var(--muted);font-size:10px}.ledger tr:nth-child(even) td{background:color-mix(in srgb,var(--b2) 55%,transparent)}.ledger th:first-child,.ledger td:first-child{position:sticky;left:0;z-index:1;background:var(--b1)}.ledger th:first-child{z-index:2;background:var(--b2)}.sort-button{border:0;background:transparent;padding:0;text-transform:uppercase;letter-spacing:.06em}.public-preview .hero,.public-preview .stats,.public-preview .status-ribbon,.public-preview .freshness,.public-preview .control-deck,.public-preview .rail,.public-preview .sectionhead,.public-preview .phasehead,.public-preview .issue:not(#public-summary),.public-preview .excluded,.public-preview footer,.public-preview .commit,.public-preview .summary-tools,.public-preview .action-needed,.public-preview .chev{display:none!important}.public-preview .layout{display:block;padding-top:28px}.public-preview #public-summary{display:block!important}.public-preview #public-summary .detail{display:block}.public-preview #public-summary summary{pointer-events:none}.public-preview .top{border-bottom-color:var(--p)}
@media(max-width:900px){.hero{grid-template-columns:1fr}.layout{grid-template-columns:1fr}.rail{position:static}.route{grid-template-columns:repeat(3,1fr);gap:6px}.route:before{display:none}.route a{grid-template-columns:26px 1fr;border:1.5px solid var(--b3);padding:7px}.route b{width:24px;height:24px}.phasehead{grid-template-columns:34px 1fr}.phasehead p{grid-column:2;text-align:left;margin-top:4px}.rail .filters{padding-top:12px}.control-deck{grid-template-columns:1fr}}
@media(max-width:560px){.top-actions .mode-button:first-child{display:none}.route{grid-template-columns:1fr 1fr}.phasehead{padding-top:30px}.hero{padding-top:34px}.hero h1{font-size:clamp(32px,9.4vw,39px);line-height:.98;letter-spacing:-.05em}.hero p{display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}.verified{padding:16px}.sectionhead h2{font-size:27px}.stats{grid-template-columns:1fr 1fr}.stat{border-right:1.5px solid var(--b3);padding:18px 12px}.stat:nth-child(odd){padding-left:0}.stat:nth-child(even){border-right:0}.num{font-size:24px}.diff-grid{grid-template-columns:1fr 1fr}.ledger tbody{min-width:0}.ledger tr{display:grid;margin:0 0 12px;border:1.5px solid var(--b3);border-radius:7px;overflow:hidden}.ledger th{display:none}.ledger td{display:grid;grid-template-columns:minmax(90px,.38fr) 1fr;gap:10px;border:0;border-bottom:1px solid var(--b3);position:static!important}.ledger td:last-child{border-bottom:0}.ledger td:before{content:attr(data-label);font:700 9px var(--body);text-transform:uppercase;color:var(--muted)}}
@media print{.top-actions,.status-ribbon,.freshness,.control-deck,.copy-link,.state-badge,.action-needed{display:none!important}.phasehead{display:grid;break-after:avoid}.route{display:none}.issue[open] summary{background:none}.ledger th:first-child,.ledger td:first-child{position:static}}
@media(max-width:900px){.rail{max-height:none;overflow:visible;padding-right:0}}
@media(forced-colors:active){.state-badge,.mode-button,.copy-link,.deck-card,.issue{border-color:CanvasText}.state-PASS{color:LinkText}.state-FAIL,.state-BLOCKED{color:MarkText}.freshness,.action-needed{border-left-color:Mark}}
.density-controls{display:flex;gap:4px}.density-controls .mode-button[aria-pressed="true"]{border-color:var(--p);color:var(--p);background:color-mix(in srgb,var(--p) 9%,var(--b1))}.control-deck{grid-template-columns:repeat(2,minmax(0,1fr))}.readiness-grid,.checkpoint-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.readiness-item,.checkpoint-item{display:flex;justify-content:space-between;gap:8px;padding:9px 10px;border:1.5px solid var(--b3);border-radius:6px;font-size:10px}.readiness-item b{font-family:var(--mono)}.graph-health{margin-top:10px;font:650 10px var(--mono);color:var(--muted)}body.density-executive .issue:not(#public-summary):not(#problem):not(#changes):not(#proof):not(#risks):not(#followup),body.density-executive .phasehead{display:none!important}body.density-executive .layout{grid-template-columns:1fr}body.density-executive .rail{display:none}body.density-forensic .issue{display:block!important}body.density-forensic .issue>.detail{display:grid!important}body.density-forensic .chev{display:none}.checkpoint-item.stale{color:var(--warn)}.checkpoint-item.current{color:var(--ok)}
@media(max-width:900px){.control-deck{grid-template-columns:1fr}}
.decision-intro{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:end;margin:0 0 22px;padding:0 0 18px;border-bottom:1.5px solid var(--b3)}.decision-intro h4{margin:0 0 7px;color:var(--bc);font-size:11px}.decision-intro p{max-width:72ch;margin:0;color:var(--muted);font-size:12px}.decision-denominator{font:650 10px/1.45 var(--mono);color:var(--muted);text-align:right}.decision-stack{display:grid;gap:12px}.decision-card{position:relative;border:1.5px solid var(--b3);border-left:4px solid var(--p);border-radius:8px;background:var(--b1);overflow:hidden}.decision-card>header{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:13px;align-items:start;padding:17px 18px 14px;background:color-mix(in srgb,var(--b2) 58%,transparent);border-bottom:1px solid var(--b3)}.decision-id{font:750 10px/1 var(--mono);letter-spacing:.08em;color:var(--p);padding-top:4px}.decision-title{margin:0;font-size:16px;line-height:1.3}.decision-state{font:700 9px/1 var(--mono);letter-spacing:.05em;color:var(--ok);border:1px solid color-mix(in srgb,var(--ok) 40%,var(--b3));border-radius:999px;padding:5px 7px}.decision-body{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(240px,.65fr)}.decision-choice{padding:18px}.decision-choice .label,.decision-facts .label{display:block;margin:0 0 6px;font:700 9px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}.decision-choice p{margin:0;font-size:13px;line-height:1.6}.decision-facts{display:grid;border-left:1px solid var(--b3)}.decision-fact{padding:13px 15px;border-bottom:1px solid var(--b3);font-size:11px;line-height:1.5}.decision-fact:last-child{border-bottom:0}.decision-evidence{display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding:11px 18px;border-top:1px solid var(--b3);font-size:10px;color:var(--muted)}.decision-evidence code{color:var(--bc);overflow-wrap:anywhere}.decision-gap{color:var(--warn)}
@media(max-width:760px){.decision-intro{grid-template-columns:1fr}.decision-denominator{text-align:left}.decision-card>header{grid-template-columns:auto 1fr}.decision-state{grid-column:2;justify-self:start}.decision-body{grid-template-columns:1fr}.decision-facts{border-left:0;border-top:1px solid var(--b3)}}
/* pr-review-route:end */
"""

SCRIPT = r'''<script>
const issues=[...document.querySelectorAll(".issue")],phases=[...document.querySelectorAll(".phasehead")],unresolved=new Set(["FAIL","BLOCKED","NOT RUN","UNKNOWN","STALE"]);
const states=element=>[...element.querySelectorAll("[data-state]")].map(node=>node.dataset.state).filter(Boolean),sectionState=issue=>{const own=issue.dataset.state;if(own)return own;const values=states(issue);if(values.some(value=>value==="FAIL"))return "FAIL";if(values.some(value=>value==="BLOCKED"))return "BLOCKED";if(values.some(value=>value==="STALE"))return "STALE";if(values.some(value=>value==="NOT RUN"))return "NOT RUN";if(values.some(value=>value==="UNKNOWN"))return "UNKNOWN";if(values.length&&values.every(value=>value==="NOT APPLICABLE"))return "NOT APPLICABLE";return values.length&&values.every(value=>value==="PASS")?"PASS":"UNKNOWN"};
issues.forEach(issue=>{const state=sectionState(issue),summary=issue.querySelector("summary"),tags=summary.querySelector(".tags"),tools=document.createElement("span");issue.dataset.governedState=state;tools.className="summary-tools";const badge=document.createElement("span");badge.className=`state-badge state-${state.replaceAll(" ","-")}`;badge.textContent=state;const copy=document.createElement("button");copy.className="copy-link";copy.type="button";copy.textContent="Link";copy.setAttribute("aria-label",`Copy link to ${issue.id}`);copy.onclick=event=>{event.preventDefault();event.stopPropagation();const url=`${location.href.split("#")[0]}#${issue.id}`;navigator.clipboard?.writeText(url);history.replaceState(null,"",`#${issue.id}`);copy.textContent="Copied";setTimeout(()=>copy.textContent="Link",1200)};tools.append(badge,copy);tags.insertBefore(tools,tags.querySelector(".chev"));if(unresolved.has(state)){const detail=issue.querySelector(".detail>div")||issue.querySelector(".detail");if(detail){const action=document.createElement("div"),refs=issue.dataset.refIds||"the required evidence ledger";action.className="action-needed";action.innerHTML=`<b>${state} — reviewer action required</b>Missing or non-current support: ${refs}. Owner: report author. Resolution: capture or refresh the named evidence against the current head, update this governed state, then reseal the dossier.`;detail.append(action)}}});
phases.forEach(phase=>{let next=phase.nextElementSibling,counts={};while(next&&!next.classList.contains("phasehead")){if(next.classList.contains("issue")){const state=next.dataset.governedState;counts[state]=(counts[state]||0)+1}next=next.nextElementSibling}const summary=document.createElement("span");summary.className="stage-state";summary.textContent=Object.entries(counts).map(([state,count])=>`${count} ${state}`).join(" · ");phase.querySelector("h3").append(summary);const route=document.querySelector(`.route a[href=\"#${phase.id}\"] span`);if(route)route.append(summary.cloneNode(true))});
const filters=[...document.querySelectorAll(".filter")],matches=(issue,kind)=>kind==="all"||(kind==="unresolved"&&unresolved.has(issue.dataset.governedState))||(kind==="changed"&&(issue.id==="post-review"||issue.id==="revisions"||issue.dataset.governedState==="STALE"))||issue.dataset.kinds.split(" ").includes(kind);filters.forEach(button=>{const kind=button.dataset.filter;button.querySelector(".count").textContent=issues.filter(issue=>matches(issue,kind)).length;button.onclick=()=>{filters.forEach(item=>item.classList.remove("active"));button.classList.add("active");issues.forEach(issue=>issue.classList.toggle("hidden",!matches(issue,kind)));phases.forEach(phase=>{let next=phase.nextElementSibling,visible=false;while(next&&!next.classList.contains("phasehead")){if(next.classList.contains("issue")&&!next.classList.contains("hidden"))visible=true;next=next.nextElementSibling}phase.classList.toggle("hidden",!visible)})}});
document.querySelectorAll(".ledger").forEach((table,tableIndex)=>{const headers=[...table.querySelectorAll("tr:first-child th")].map(th=>th.textContent.trim());table.querySelectorAll("tr").forEach((row,rowIndex)=>{if(rowIndex&& !row.id){const record=row.dataset.recordId||row.cells[0]?.textContent.trim().match(/[A-Z]+-\d+/)?.[0];if(record)row.id=`record-${record.toLowerCase()}`}row.querySelectorAll("td").forEach((cell,index)=>cell.dataset.label=headers[index]||`Column ${index+1}`)});table.querySelectorAll("th").forEach((th,index)=>{if(!th.textContent.trim())return;const label=th.textContent;th.textContent="";const button=document.createElement("button");button.className="sort-button";button.type="button";button.textContent=label;button.onclick=()=>{const body=table.tBodies[0]||table,rows=[...body.querySelectorAll("tr")].filter(row=>row.querySelector("td")),direction=th.dataset.direction==="asc"?-1:1;rows.sort((a,b)=>a.cells[index].textContent.localeCompare(b.cells[index].textContent,undefined,{numeric:true})*direction).forEach(row=>body.append(row));th.dataset.direction=direction===1?"asc":"desc"};th.append(button)})});
const consumers={};document.querySelectorAll("[data-ref-ids]").forEach(node=>(node.dataset.refIds||"").split(/\s+/).filter(Boolean).forEach(id=>(consumers[id]??=new Set()).add(node.dataset.recordId||node.closest(".issue")?.id||node.id||"record")));document.querySelectorAll("#evidence-manifest tr[data-record-id]").forEach(row=>{const id=row.dataset.recordId,used=[...(consumers[id]||[])].filter(value=>value!=="evidence-manifest");if(used.length){const cell=row.cells[row.cells.length-1],back=document.createElement("span");back.className="evidence-uses";back.textContent=`Used by: ${used.join(" · ")}`;cell.append(back)}});
const stale=issues.filter(issue=>issue.dataset.governedState==="STALE"),failed=issues.filter(issue=>["FAIL","BLOCKED"].includes(issue.dataset.governedState)),open=issues.filter(issue=>unresolved.has(issue.dataset.governedState)),passed=issues.filter(issue=>issue.dataset.governedState==="PASS"),posture=failed.length?"BLOCKED":stale.length?"STALE":open.length?"DRAFT":"REVIEWABLE";document.querySelectorAll("[data-posture]").forEach(node=>node.textContent=posture);document.querySelector("[data-proven]").textContent=`${passed.length} / ${issues.length} sections`;document.querySelector("[data-blockers]").textContent=failed.length?`${failed.length} blocking sections`:stale.length?`${stale.length} stale sections`:open.length?`${open.length} unresolved sections`:"None observed";document.querySelector("[data-next]").textContent=failed[0]?.id||stale[0]?.id||open[0]?.id||"human public-summary audit";if(stale.length){const banner=document.querySelector(".freshness");banner.classList.add("show");banner.textContent=`This dossier contains ${stale.length} stale governed section${stale.length===1?"":"s"}. Refresh decisive evidence against the current PR head before relying on readiness claims.`}
const fileRows=[...document.querySelectorAll("#changes tr[data-file]")],classify=path=>path.includes("test/")||path.includes("_test")?"Tests":path.match(/docs?|README|CHANGELOG/i)?"Documentation":path.match(/mix\.lock|package-lock|Cargo\.lock|requirements/i)?"Dependencies":path.match(/generated|priv\/static|\.min\./i)?"Generated":"Implementation",counts={Implementation:0,Tests:0,Documentation:0,Dependencies:0,Generated:0};fileRows.forEach(row=>counts[classify(row.dataset.file)]++);document.querySelectorAll("[data-diff-kind]").forEach(node=>node.querySelector("b").textContent=counts[node.dataset.diffKind]||0);
document.querySelector("[data-delta-commits]").textContent=document.querySelectorAll("#post-review tr[data-state]:not(:first-child)").length;document.querySelector("[data-delta-stale]").textContent=stale.length;document.querySelector("[data-delta-review]").textContent=document.querySelectorAll("#review-threads tr[data-record-id]").length;document.querySelector("[data-delta-revisions]").textContent=Math.max(0,document.querySelectorAll("#revisions tr").length-2);
document.querySelector("[data-filter-jump]").onclick=()=>document.querySelector('[data-filter="changed"]').click();const mode=document.querySelector("[data-public-mode]"),publicSummary=document.querySelector("#public-summary");mode.onclick=()=>{document.body.classList.toggle("public-preview");if(document.body.classList.contains("public-preview"))publicSummary.open=true;mode.textContent=document.body.classList.contains("public-preview")?"Return to private dossier":"Preview public-safe fields"};
const densityButtons=[...document.querySelectorAll("[data-density]")];densityButtons.forEach(button=>button.onclick=()=>{document.body.classList.remove("density-executive","density-forensic");if(button.dataset.density!=="reviewer")document.body.classList.add(`density-${button.dataset.density}`);densityButtons.forEach(item=>item.setAttribute("aria-pressed",String(item===button)));localStorage.setItem("pr-report-density",button.dataset.density)});const savedDensity=localStorage.getItem("pr-report-density")||"reviewer";densityButtons.find(button=>button.dataset.density===savedDensity)?.click();
addEventListener("DOMContentLoaded",()=>{const machineTag=document.querySelector("#pr-report-manifest");if(machineTag){try{const machine=JSON.parse(machineTag.textContent),ready=machine.readiness;document.querySelector("[data-ready-sections]").textContent=`${ready.sections.satisfied}/${ready.sections.total}`;document.querySelector("[data-ready-claims]").textContent=`${ready.claims.supported}/${ready.claims.total}`;document.querySelector("[data-ready-evidence]").textContent=`${ready.evidence.used}/${ready.evidence.total}`;document.querySelector("[data-ready-review]").textContent=`${ready.review_checkpoints.acknowledged}/${ready.review_checkpoints.total}`;const graph=machine.graph_issues,total=graph.dangling_references.length+graph.unused_evidence.length+graph.unsupported_claims.length;document.querySelector("[data-graph-health]").textContent=total?`${total} evidence-graph issue${total===1?"":"s"} require resolution`:"Claim and evidence graph is closed";const acknowledgements=new Map(machine.review_acknowledgements.map(item=>[item.checkpoint,item]));document.querySelectorAll("[data-checkpoint]").forEach(node=>{const item=acknowledgements.get(node.dataset.checkpoint);node.classList.add(item?.current?"current":"stale");node.querySelector("b").textContent=item?.current?"CURRENT":item?"STALE":"OPEN"})}catch(error){document.querySelector("[data-graph-health]").textContent="Machine manifest is unreadable"}}});
if(location.hash==="#public-preview")mode.click();else if(location.hash){const target=document.querySelector(location.hash);if(target?.tagName==="DETAILS")target.open=true}
</script>'''


def phase_markup(index: int, slug: str, title: str, description: str) -> str:
    return (
        f'<div class="phasehead" id="phase-{slug}"><span class="phase-index">'
        f'{index:02d}</span><h3>{title}</h3><p>{description}</p></div>'
    )


def rail_markup(scope: str) -> str:
    links = "".join(
        f'<a href="#phase-{slug}"><b>{index:02d}</b><span>{title}</span></a>'
        for index, (slug, title, _, _) in enumerate(STAGES, 1)
    )
    return (
        '<aside class="rail"><div class="rail-kicker">Reviewer route</div>'
        f'<nav class="route" aria-label="PR report stages">{links}</nav>'
        '<h2>Filter evidence</h2><div class="filters">'
        '<button class="filter active" data-filter="all">All sections <span class="count">29</span></button>'
        '<button class="filter" data-filter="unresolved">Only unresolved <span class="count">0</span></button>'
        '<button class="filter" data-filter="changed">Since review <span class="count">0</span></button>'
        '<button class="filter" data-filter="runtime">Runtime <span class="count">29</span></button>'
        '<button class="filter" data-filter="path">Code path <span class="count">29</span></button>'
        '<button class="filter" data-filter="high">High <span class="count">29</span></button>'
        '<button class="filter" data-filter="medium">Medium / low <span class="count">29</span></button>'
        f'</div><div class="scope">{scope}</div></aside>'
    )


def replace_legacy_trial_placeholders(source: str) -> str:
    """Replace the old blanket trial filler with section-specific evidence gaps."""
    legacy = re.compile(
        r"Not yet reconstructed from authoritative evidence in (?:this )?(?:trial )?draft\."
    )

    def rewrite_section(match: re.Match[str]) -> str:
        block = match.group(0)
        title_match = re.search(r"<h3>(.*?)</h3>", block, re.S)
        title = re.sub(r"<.*?>", "", title_match.group(1)).strip() if title_match else "section"
        replacement = (
            "UNKNOWN — no cited authoritative evidence currently establishes "
            f"this requested {title.lower()} fact."
        )
        return legacy.sub(replacement, block)

    source = re.sub(r'<details id="[^"]+".*?</details>', rewrite_section, source, flags=re.S)
    return legacy.sub(
        "UNKNOWN — no cited authoritative evidence currently establishes this requested report fact.",
        source,
    )


def transform(source: str) -> str:
    source = re.sub(r'<!-- review-controls:begin -->.*?<!-- review-controls:end -->',
                    '', source, flags=re.S)
    source = re.sub(r'<div class="top-actions">.*?</div>\s*</header>',
                    '</header>', source, flags=re.S)
    source = re.sub(r'\s*/\* pr-review-route:begin \*/.*?'
                    r'/\* pr-review-route:end \*/\s*',
                    "\n", source, flags=re.S)
    source = source.replace("</style>", "\n" + CSS.strip() + "\n</style>", 1)
    source = re.sub(
        r'(<meta name="artifact\.(?:report-digest|evidence-manifest-digest)" content=")[^"]*(">)',
        r'\1UNSEALED\2', source,
    )
    source = re.sub(
        r'<aside class="verified">.*?</aside>',
        '<aside class="verified"><h2>Review posture</h2><ul>'
        '<li><span>Posture</span><strong data-posture>DRAFT</strong></li>'
        '<li><span>Proven</span><strong data-proven>Calculating…</strong></li>'
        '<li><span>Blocked by</span><strong data-blockers>Calculating…</strong></li>'
        '<li><span>Next review action</span><strong data-next>Calculating…</strong></li>'
        '</ul></aside>', source, count=1, flags=re.S,
    )
    source = re.sub(
        r'<h1>(.*?)<br><span>(.*?)</span></h1>',
        r'<h1>\1</h1><div class="status-summary">\2</div>',
        source, count=1, flags=re.S,
    )
    controls = '''<!-- review-controls:begin -->
<section class="status-ribbon" aria-label="Dossier status"><span class="posture" data-posture>DRAFT</span><span>Current-head dossier</span><span>Evidence governed</span><span>Private canonical view</span></section>
<div class="freshness" role="status" aria-live="polite"></div>
<!-- review-controls:end -->'''
    source = re.sub(r'(</section>\s*)(<section class="stats">)',
                    lambda match: match.group(1) + controls + match.group(2),
                    source, count=1)
    deck = '''<!-- review-controls:begin -->
<section class="control-deck" aria-label="Reviewer briefing">
  <article class="deck-card"><h2>Executive change map</h2><p>Fast scope orientation from the authoritative changed-file denominator. The complete ledger remains in Change.</p><div class="diff-grid"><div class="diff-item" data-diff-kind="Implementation"><b>0</b><span>Implementation</span></div><div class="diff-item" data-diff-kind="Tests"><b>0</b><span>Tests</span></div><div class="diff-item" data-diff-kind="Documentation"><b>0</b><span>Documentation</span></div><div class="diff-item" data-diff-kind="Dependencies"><b>0</b><span>Dependencies</span></div><div class="diff-item" data-diff-kind="Generated"><b>0</b><span>Generated</span></div><div class="diff-item"><b>Exact</b><span>GitHub denominator</span></div></div></article>
  <article class="deck-card"><h2>Since the last review</h2><p>A compact delta assembled from report revisions, post-review changes, review threads, and stale evidence.</p><div class="delta-list"><div class="delta-item"><span>Post-review change records</span><b data-delta-commits>0</b></div><div class="delta-item"><span>Stale governed sections</span><b data-delta-stale>0</b></div><div class="delta-item"><span>Review thread records</span><b data-delta-review>0</b></div><div class="delta-item"><span>Report revisions after initial</span><b data-delta-revisions>0</b></div></div><button class="mode-button" type="button" data-filter-jump>Show review delta</button></article>
  <article class="deck-card"><h2>Evidence readiness</h2><p>Explicit denominators replace a synthetic confidence score.</p><div class="readiness-grid"><div class="readiness-item"><span>Sections</span><b data-ready-sections>—</b></div><div class="readiness-item"><span>Claims</span><b data-ready-claims>—</b></div><div class="readiness-item"><span>Evidence used</span><b data-ready-evidence>—</b></div><div class="readiness-item"><span>Review gates</span><b data-ready-review>—</b></div></div><div class="graph-health" data-graph-health>Compile the machine manifest to calculate graph health.</div></article>
  <article class="deck-card"><h2>Reviewer checkpoints</h2><p>Digest- and head-bound acknowledgements become stale after material report changes.</p><div class="checkpoint-grid"><div class="checkpoint-item" data-checkpoint="problem"><span>Problem</span><b>OPEN</b></div><div class="checkpoint-item" data-checkpoint="scope"><span>Scope</span><b>OPEN</b></div><div class="checkpoint-item" data-checkpoint="architecture"><span>Architecture</span><b>OPEN</b></div><div class="checkpoint-item" data-checkpoint="tests"><span>Tests</span><b>OPEN</b></div><div class="checkpoint-item" data-checkpoint="security-privacy"><span>Security / privacy</span><b>OPEN</b></div><div class="checkpoint-item" data-checkpoint="operations"><span>Operations</span><b>OPEN</b></div><div class="checkpoint-item" data-checkpoint="documentation"><span>Documentation</span><b>OPEN</b></div><div class="checkpoint-item" data-checkpoint="public-summary"><span>Public summary</span><b>OPEN</b></div></div></article>
</section>
<!-- review-controls:end -->'''
    source = re.sub(r'(</section>\s*)(<div class="layout">)',
                    lambda match: match.group(1) + deck + match.group(2),
                    source, count=1)
    source = re.sub(
        r'(<header class="top">.*?)(</header>)',
        lambda match: match.group(1) + '<div class="top-actions"><div class="density-controls" aria-label="Report density"><button class="mode-button" type="button" data-density="executive" aria-pressed="false">Executive</button><button class="mode-button" type="button" data-density="reviewer" aria-pressed="true">Reviewer</button><button class="mode-button" type="button" data-density="forensic" aria-pressed="false">Forensic</button></div><button class="mode-button" type="button" data-public-mode>Preview public-safe fields</button></div>' + match.group(2),
        source, count=1, flags=re.S,
    )

    rail = re.search(r'<aside class="rail">(.*?)</aside>', source, re.S)
    if not rail:
        raise ValueError("PR report rail not found")
    scope_match = re.search(r'<div class="scope">(.*?)</div>', rail.group(0), re.S)
    scope = scope_match.group(1) if scope_match else "Private lifecycle scope and exact target are recorded in provenance."
    source = source[:rail.start()] + rail_markup(scope) + source[rail.end():]

    issues_match = re.search(r'(<div class="issues">)(.*?)(</div>\s*'
                             r'<section class="excluded">)',
                             source, re.S)
    if not issues_match:
        raise ValueError("PR report issue collection not found")
    body = issues_match.group(2)
    blocks = {
        match.group(1): match.group(0)
        for match in re.finditer(r'<details id="([^"]+)".*?</details>', body, re.S)
    }
    expected = [item for _, _, _, ids in STAGES for item in ids]
    missing = [item for item in expected if item not in blocks]
    extras = [item for item in blocks if item not in expected]
    if missing or extras:
        raise ValueError(f"section denominator mismatch: missing={missing} extras={extras}")
    rebuilt = []
    for index, (slug, title, description, ids) in enumerate(STAGES, 1):
        rebuilt.append(phase_markup(index, slug, title, description))
        rebuilt.extend(blocks[item] for item in ids)
    source = (source[:issues_match.start(2)] + "\n" + "\n".join(rebuilt) + "\n" +
              source[issues_match.end(2):])
    source = re.sub(r'<script>.*?</script>', lambda _: SCRIPT,
                    source, count=1, flags=re.S)
    return replace_legacy_trial_placeholders(source)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    for report in args.reports:
        original = report.read_text()
        updated = transform(original)
        report.write_text(updated)
        print(report.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
