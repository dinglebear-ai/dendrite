#!/usr/bin/env python3
"""Seed a new PR-report draft from discover-pr-context.py JSON."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re


def unknown_for(prompt: str) -> str:
    """Turn an unfilled template prompt into a precise, reviewable evidence gap."""
    normalized = re.sub(r"\s+", " ", prompt).strip().rstrip(".")
    return f"UNKNOWN — no cited authoritative evidence currently establishes: {normalized}."


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def prose_summary(body: str, fallback: str) -> str:
    """Return the first useful prose paragraph from a Markdown PR body."""
    for paragraph in re.split(r"\n\s*\n", body.strip()):
        cleaned = re.sub(r"<!--.*?-->", "", paragraph, flags=re.S).strip()
        if not cleaned or cleaned.startswith(("#", "```", "- [")):
            continue
        cleaned = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        if len(cleaned) >= 24:
            return cleaned
    return fallback


def markdown_section(body: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        body,
        flags=re.M | re.S | re.I,
    )
    return match.group(1).strip() if match else ""


def bullets(markdown: str) -> list[str]:
    return [re.sub(r"^[-*]\s+", "", line).strip()
            for line in markdown.splitlines() if re.match(r"^[-*]\s+", line)]


def replace_detail(source: str, section_id: str, content: str) -> str:
    return re.sub(
        rf'(<details id="{re.escape(section_id)}".*?</summary>).*?</details>',
        lambda match: match.group(1) + content + "</details>",
        source,
        count=1,
        flags=re.S,
    )


def set_record_evidence(source: str, record_id: str, evidence_ids: str) -> str:
    """Set the structured evidence edge for one governed report record."""
    pattern = rf'(<[^>]+\bdata-record-id="{re.escape(record_id)}"[^>]*\bdata-ref-ids=")[^"]*(")'
    updated, count = re.subn(
        pattern,
        lambda match: match.group(1) + esc(evidence_ids) + match.group(2),
        source,
        count=1,
    )
    if count != 1:
        raise ValueError(f"missing data-ref-ids for report record: {record_id}")
    return updated


def set_section_evidence(
    source: str, section_id: str, evidence_ids: str, state: str = "UNKNOWN", reason: str = ""
) -> str:
    """Attach evidence and governed state to one report section."""
    pattern = rf'<details id="{re.escape(section_id)}"[^>]*>'
    match = re.search(pattern, source)
    if not match:
        raise ValueError(f"missing report section: {section_id}")
    opening = re.sub(r'\sdata-(?:state|reason|ref-ids)="[^"]*"', "", match.group(0))
    attributes = (
        f' data-state="{esc(state)}" data-reason="{esc(reason)}"'
        f' data-ref-ids="{esc(evidence_ids)}"'
    )
    return source[:match.start()] + opening[:-1] + attributes + ">" + source[match.end():]


def unseal_report(source: str) -> str:
    """Mark a reseeded report unsealed so the normal sealing gate can refresh it."""
    for name in ("report-digest", "evidence-manifest-digest"):
        source = re.sub(
            rf'(<meta name="artifact\.{re.escape(name)}" content=")[^"]*(">)',
            lambda match: match.group(1) + "UNSEALED" + match.group(2),
            source,
            count=1,
        )
    return source


def decision_candidates(commits: list[dict[str, object]]) -> list[dict[str, str]]:
    """Return a bounded set of review candidates; commits are not decisions."""
    themes = [
        ("Safety and recovery behavior", ("harden", "fail closed", "recovery", "cleanup")),
        ("Concurrency and effect ordering", ("serialize", "race", "atomic", "effect")),
        ("Credential and persistence boundary", ("credential", "authenticate", "durable", "persist", "intent")),
        ("User-visible feature scope", ("feat(", "add ", "support ", "introduce ")),
    ]
    candidates: list[dict[str, str]] = []
    for title, needles in themes:
        matches = [item for item in commits
                   if any(needle in str(item["message"]).splitlines()[0].lower()
                          for needle in needles)]
        if not matches:
            continue
        candidates.append({
            "title": title,
            "choice": "; ".join(str(item["message"]).splitlines()[0] for item in matches),
            "evidence": " · ".join(str(item["sha"])[:8] for item in matches),
        })
    return candidates[:6]


def session_rows(context: dict[str, object], evidence: dict[str, object] | None = None) -> str:
    """Render de-duplicated Cortex lineage, resolving local transcript paths."""
    if evidence:
        rows = []
        for item in evidence.get("sessions", []):
            analysis = item.get("analysis") or {}
            boundary = (
                f'{analysis.get("records_scanned", 0)} records fully scanned; '
                f'{analysis.get("full_scan_boundary", "snapshot boundary unknown")}; '
                f'{len(analysis.get("matched_excerpts", []))} bounded scope excerpts retained; '
                f'sha256={analysis.get("source_sha256", "UNKNOWN")}; '
                f'classification={item.get("classification", "candidate")}; '
                f'sources={", ".join(item.get("sources", [])) or "UNKNOWN"}.'
            )
            rows.append(
                f'<tr><td>{esc(str(item.get("tool", "UNKNOWN")).title())}</td>'
                '<td>Model/version not established by transcript metadata</td>'
                f'<td>{esc(str(item.get("classification", "candidate")).replace("-", " ").title())} PR lifecycle evidence</td>'
                f'<td class="mono">{esc(item.get("session_id", "UNKNOWN"))}</td>'
                f'<td class="mono">{esc(analysis.get("path") or "UNKNOWN — no local transcript")}</td>'
                f'<td>{esc(analysis.get("first_seen") or item.get("first_seen") or "UNKNOWN")} → '
                f'{esc(analysis.get("last_seen") or item.get("last_seen") or "UNKNOWN")}; {esc(boundary)}</td></tr>'
            )
        if rows:
            return "".join(rows)
    local_by_id: dict[str, dict[str, object]] = {}
    for item in context["local_transcripts"]:
        if item["is_subagent_transcript"]:
            continue
        local_by_id.setdefault(str(item["session_id"]), item)
    seen: set[tuple[str, str, str]] = set()
    rows: list[str] = []
    for item in context["cortex_sessions"]:
        key = (str(item["tool"]), str(item["session_id"]), str(item["project"]))
        if key in seen:
            continue
        seen.add(key)
        local = local_by_id.get(str(item["session_id"]))
        transcript = (str(local["path"]) if local else
                      "UNKNOWN — Cortex search does not expose the absolute source transcript path")
        queries = ", ".join(str(query) for query in item.get("queries", []))
        rows.append(
            f'<tr><td>{esc(str(item["tool"]).title())}</td>'
            '<td>Model/version not established by indexed transcript metadata</td>'
            '<td>PR lifecycle session matched by repository-bound lineage keys</td>'
            f'<td class="mono">{esc(item["session_id"])}</td>'
            f'<td class="mono">{esc(transcript)}</td>'
            f'<td>{esc(item.get("first_seen") or "UNKNOWN")} → '
            f'{esc(item.get("last_seen") or "UNKNOWN")}; host={esc(item.get("hostname") or "UNKNOWN")}; '
            f'project={esc(item.get("project") or "UNKNOWN")}; matched {esc(queries)}.</td></tr>'
        )
    if rows:
        return "".join(rows)
    return ('<tr><td>UNKNOWN</td><td>UNKNOWN</td><td>No repository-bound Cortex '
            'session match was found.</td><td>UNKNOWN</td><td>UNKNOWN</td>'
            '<td>Continuity gap retained; do not infer that no session existed.</td></tr>')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--session-evidence", type=Path)
    parser.add_argument("--session-evidence-id", default="E-003")
    args = parser.parse_args()
    context = json.loads(args.context.read_text())
    session_evidence = json.loads(args.session_evidence.read_text()) if args.session_evidence else None
    pr = context["pr"]
    source = args.report.read_text()
    worktree_match = re.search(r'<meta name="artifact\.worktree" content="([^"]*)">', source)
    worktree = html.unescape(worktree_match.group(1)) if worktree_match else "UNKNOWN"

    strong_artifacts = [item for item in context["artifact_matches"] if item["score"] >= 10]
    related = []
    root = Path(__file__).resolve().parents[1]
    for item in strong_artifacts:
        path = Path(item["path"])
        if path.suffix == ".html":
            related.append(str(path.relative_to(root)))
    related = list(dict.fromkeys(related))
    source = re.sub(
        r'(<meta name="artifact\.related" content=")[^"]*(">)',
        lambda match: match.group(1) + esc(", ".join(related)) + match.group(2), source, count=1,
    )

    file_rows = "".join(
        '<tr data-file="{0}"><td class="mono">{0}</td><td>modify</td>'
        '<td>PR implementation surface</td>'
        '<td>Included in the GitHub PR changed-file denominator.</td>'
        '<td>Exact behavior is described by the PR body and E-001; independent diff review remains required.</td></tr>'.format(esc(path))
        for path in pr["files"]
    )
    source = re.sub(r'<tr data-file="\{\{repo-relative path\}\}">.*?</tr>', file_rows, source, count=1)

    source = re.sub(
        r'<section class="stats">.*?</section>',
        '<section class="stats">'
        f'<div class="stat"><div class="num">{len(pr["files"])}</div><div class="label">Files changed</div></div>'
        f'<div class="stat"><div class="num">{len(pr["commits"])}</div><div class="label">Commits in PR</div></div>'
        '<div class="stat"><div class="num">Evidence</div><div class="label">Verification manifest</div></div>'
        '<div class="stat"><div class="num">Ledger</div><div class="label">Required follow-up</div></div>'
        '</section>', source, count=1, flags=re.S,
    )

    rows = session_rows(context, session_evidence)
    source = re.sub(
        r'(<details id="sessions".*?<table class="ledger">.*?'
        r'<tr><th>Agent / human</th>.*?</tr>).*?(</table>)',
        lambda match: match.group(1) + rows + match.group(2),
        source, count=1, flags=re.S,
    )
    if session_evidence:
        cortex_query = session_evidence.get("cortex_query") or context.get("cortex_query") or {}
        selected_count = len(session_evidence.get("sessions", []))
        deduplicated_count = session_evidence.get("denominator", {}).get("deduplicated_sessions", "UNKNOWN")
        cortex_detail = cortex_query.get("reason") or (
            f'{cortex_query.get("session_count", 0)} Cortex candidate session(s) matched.'
        )
        session_caption = (
            f'{selected_count} selected transcript snapshot(s) from {deduplicated_count} de-duplicated candidates. '
            f'Cortex query status: {cortex_query.get("status", "UNKNOWN")}; '
            f'{cortex_detail}'
        )
        session_boundary = session_evidence.get(
            "proof_boundary",
            "Transcript coverage boundary was not recorded; do not infer complete lifecycle coverage.",
        )
        source = re.sub(
            r'(<details id="sessions".*?<table class="ledger"><caption>).*?(</caption>)',
            lambda match: match.group(1) + esc(session_caption) + match.group(2),
            source,
            count=1,
            flags=re.S,
        )
        source = re.sub(
            r'(<details id="sessions".*?<div class="limit">).*?(</div>\s*</div>\s*</div>\s*</details>)',
            lambda match: match.group(1) + esc(session_boundary) + match.group(2),
            source,
            count=1,
            flags=re.S,
        )
        primary_complete = any(
            item.get("classification") == "primary" and (item.get("analysis") or {}).get("full_scan")
            for item in session_evidence.get("sessions", [])
        )
        session_reason = "" if primary_complete else (
            "No explicitly identified primary lifecycle transcript was fully scanned; ranked candidates remain discovery leads."
        )
        source = set_section_evidence(
            source, "sessions", args.session_evidence_id,
            "PASS" if primary_complete else "UNKNOWN", session_reason
        )
        source = set_section_evidence(
            source, "tooling", args.session_evidence_id, "UNKNOWN",
            "Transcript tool names and counts are captured, but arguments, outputs, failures, and retries still require reviewed evidence."
        )
        source = set_section_evidence(
            source, "timeline", f"E-001 {args.session_evidence_id}", "UNKNOWN",
            "Commit order and bounded transcript excerpts are captured, but the complete lifecycle chronology still requires review."
        )

    summary_items = bullets(markdown_section(pr["body"], "Summary"))
    if not summary_items:
        summary_items = [prose_summary(pr["body"], pr["title"])]
    summary_html = "".join(f"<li>{esc(item)}</li>" for item in summary_items)
    source = replace_detail(
        source,
        "public-summary",
        '<div class="detail full"><div><h4>Copy-safe content candidate</h4>'
        f'<p><strong>{esc(pr["title"])}</strong></p><ul class="checklist">{summary_html}</ul>'
        f'<div class="evidence">Source: E-001, GitHub PR body captured at head {esc(pr["head_sha"])}.</div>'
        '<div class="limit">Candidate only: a human must audit the exact copied payload before publication.</div>'
        '</div></div>',
    )

    source = replace_detail(
        source,
        "provenance",
        '<div class="detail"><div><h4>Immutable source identity</h4><table class="ledger">'
        '<caption>GitHub API identity captured in E-001.</caption><tr><th>Field</th><th>Exact value</th></tr>'
        f'<tr><td>Repository / PR</td><td>{esc(pr["repository"])} · <a href="{esc(pr["url"])}">#{esc(pr["number"])}</a> · {esc(pr["state"])}</td></tr>'
        f'<tr><td>Base / merge base</td><td>{esc(pr["base_branch"])} @ {esc(pr["base_sha"])} · {esc(pr["merge_base"])}</td></tr>'
        f'<tr><td>Head</td><td>{esc(pr["head_branch"])} @ {esc(pr["head_sha"])}</td></tr>'
        f'<tr><td>Worktree</td><td class="mono">{esc(worktree)}</td></tr>'
        f'<tr><td>PR time</td><td>{esc(pr["created_at"])} → {esc(pr["updated_at"])}</td></tr>'
        '</table><div class="fix"><b>Authority boundary</b> GitHub identity and the local path are observed; runtime/toolchain facts require separate captured commands.</div></div>'
        '<aside><h4>Runtime inventory gap</h4><div class="evidence">UNKNOWN — no immutable environment inventory is linked yet.</div>'
        '<div class="limit">Do not infer OS, tool versions, or dirty state from the PR API.</div></aside></div>',
    )

    commit_rows = "".join(
        f'<tr><td>{esc(pr["created_at"] if index == 0 else "Order " + str(index + 1))}</td>'
        f'<td>Commit</td><td>{esc(item["message"].splitlines()[0])}</td>'
        f'<td class="mono">{esc(item["sha"])} · E-001</td><td>PR history advanced</td></tr>'
        for index, item in enumerate(pr["commits"])
    )
    source = replace_detail(
        source,
        "timeline",
        '<div class="detail full"><div><table class="ledger"><caption>Authoritative PR commit order from E-001; session-level chronology remains additive.</caption>'
        '<tr><th>Timestamp / order</th><th>Phase</th><th>Action and rationale</th><th>Result / evidence</th><th>State transition</th></tr>'
        f'{commit_rows}</table><div class="limit">Commit order proves repository history, not every discussion or abandoned approach.</div></div></div>',
    )

    candidates = decision_candidates(pr["commits"])
    decision_cards = "".join(
        f'<article class="decision-card" data-record-id="DEC-{index:03d}" data-state="UNKNOWN" data-reason="Commit history identifies a decision candidate, but does not establish alternatives or attributable rationale." data-ref-ids="E-001">'
        f'<header><span class="decision-id">DEC-{index:03d}</span><h4 class="decision-title">{esc(item["title"])}</h4><span class="decision-state decision-gap">NEEDS RATIONALE</span></header>'
        f'<div class="decision-body"><div class="decision-choice"><span class="label">Observed direction</span><p>{esc(item["choice"])}</p></div>'
        '<div class="decision-facts"><div class="decision-fact"><span class="label">Alternatives</span><span class="decision-gap">Not established by commit metadata; recover from cited transcripts, review artifacts, or official sources.</span></div>'
        '<div class="decision-fact"><span class="label">Consequences / rollback</span>Revert or supersede the bounded implementation after review; exact blast radius remains to be documented.</div>'
        '<div class="decision-fact"><span class="label">What would change this</span>Contrary repository behavior, official documentation, or reproducible runtime evidence.</div></div></div>'
        f'<footer class="decision-evidence"><span class="label">Evidence</span><code>E-001 · commits {esc(item["evidence"])}</code></footer></article>'
        for index, item in enumerate(candidates, 1)
    ) or ('<article class="decision-card" data-record-id="DEC-001" data-state="UNKNOWN" data-reason="No material decision candidate was recoverable from commit metadata." data-ref-ids="E-001"><header><span class="decision-id">DEC-001</span><h4 class="decision-title">No material decision reconstructed</h4><span class="decision-state decision-gap">EVIDENCE GAP</span></header><div class="decision-body"><div class="decision-choice"><span class="label">Required next step</span><p>Recover attributable rationale from the PR discussion, transcripts, review artifacts, code, or official documentation.</p></div><div class="decision-facts"><div class="decision-fact"><span class="label">Boundary</span>A missing decision record is explicit; no rationale is inferred.</div></div></div><footer class="decision-evidence"><span class="label">Evidence</span><code>E-001 · commit inventory only</code></footer></article>')
    source = replace_detail(
        source,
        "decisions",
        '<div class="detail full"><div><div class="decision-intro"><div><h4>Reviewer decision map</h4><p>Material themes inferred from commit subjects are candidates for reconstruction, not automatically accepted decisions. Commit chronology remains in the change map.</p></div>'
        f'<div class="decision-denominator">{len(candidates) or 1} candidate themes<br>E-001 · PR commit inventory</div></div><div class="decision-stack">{decision_cards}</div>'
        '<div class="limit">Commit metadata establishes what changed, not why alternatives lost. Promote a candidate to PASS only after attributable rationale and primary evidence are linked.</div></div></div>',
    )

    verification = bullets(markdown_section(pr["body"], "Verification"))
    test_rows = "".join(
        f'<tr data-record-id="TEST-{index:03d}" data-state="UNKNOWN" data-reason="PR-body claim captured; immutable execution output not yet linked." data-ref-ids="E-001" data-source-sha="{esc(pr["head_sha"])}"><td>TEST-{index:03d}</td><td>{esc(item)}</td><td>Environment not established</td><td>As stated in PR body</td><td>Claim captured in E-001; execution receipt required</td><td>UNKNOWN</td><td>E-001</td></tr>'
        for index, item in enumerate(verification, 1)
    ) or f'<tr data-record-id="TEST-001" data-state="UNKNOWN" data-reason="No Verification section was found in the captured PR body." data-ref-ids="E-001" data-source-sha="{esc(pr["head_sha"])}"><td>TEST-001</td><td>No command captured</td><td>Unknown</td><td>Unknown</td><td>No PR-body verification claim</td><td>UNKNOWN</td><td>E-001</td></tr>'
    source = replace_detail(
        source,
        "testing",
        '<div class="detail full"><div><table class="ledger"><caption>Verification claims from the captured PR body; state remains UNKNOWN until immutable command output is linked.</caption>'
        '<tr><th>Test</th><th>Exact command / scenario</th><th>Environment</th><th>Expected</th><th>Actual</th><th>State</th><th>Evidence</th></tr>'
        f'{test_rows}</table><div class="limit">PR prose is evidence of what was claimed, not independent proof that the command ran or passed.</div></div></div>',
    )
    source = set_record_evidence(source, "REV-001", "E-002")

    replacements = {
        "{{org/repo}}": pr["repository"],
        "{{base…head}}": f'{pr["base_branch"]}…{pr["head_branch"]}',
        "{{head SHA}}": pr["head_sha"][:12],
        "{{PR number and state}}": f'PR #{pr["number"]} · {pr["state"]}',
        "{{Problem or feature.}}": pr["title"],
        "{{Verified outcome.}}": "Draft reconstruction; outcome requires exact-head evidence and gate reconciliation.",
        "{{One sentence: why this PR exists, what exact behavior changed, and the strongest current proof. This private report is the canonical map for the complete PR lifecycle.}}":
            prose_summary(pr["body"], pr["title"]),
        "{{updated date/time/time zone}}": pr["updated_at"],
        "{{short SHA → short SHA}}": f'{pr["merge_base"][:8]} → {pr["head_sha"][:8]}',
        "{{n / n / blocked}}": "See E-002 live PR snapshot",
        "{{resolved / open}}": "See E-002 live PR snapshot",
        "{{clean · draft/review}}": "worktree identity verified · report draft",
        "{{files count}}": str(len(pr["files"])),
        "{{commits count}}": str(len(pr["commits"])),
        "{{Filter label}}": "Inspect dossier",
        "{{n}}": str(len(pr["files"])),
        "{{Scope of this artifact — what it covers and what it deliberately does not.}}":
            f'Draft reconstruction of PR #{pr["number"]} from GitHub, matched artifacts, and local transcript evidence. Cortex query status: {((session_evidence or {}).get("cortex_query") or context.get("cortex_query") or {}).get("status", "UNKNOWN")}. It does not claim final readiness until exact-head proof and current gates are independently recaptured.',
        "{{target commit / path}}": pr["head_sha"],
        "{{Who experiences what, in which supported environment.}}":
            prose_summary(pr["body"], pr["title"]),
        "{{Minimal deterministic reproduction with inputs and preconditions.}}":
            "Use the reproduction and verification commands recorded in the PR body or linked evidence against immutable base and head snapshots.",
        "{{Observable consequence, frequency, severity, and blast radius.}}":
            "See the PR body and E-001 for the currently claimed impact; severity and frequency require independent evidence.",
        "{{Exact behavior that must be true for this PR to succeed, including deliberate non-goals.}}":
            "Every behavior claimed by the PR must be proven at the exact head, with a base comparison when the claim is causal.",
        "{{full head SHA}}": pr["head_sha"],
        "{{reason}}": "Draft reconstruction is incomplete; see the section boundary and E-001/E-002.",
        "{{Registry/spec/issue/contract and exact version or SHA}}":
            f'GitHub PR #{pr["number"]} changed-file set and PR body at head {pr["head_sha"]}.',
        "{{Observable requirement}}": f'The {len(pr["files"])} changed files collectively implement the PR title: {pr["title"]}.',
        "{{Paths}}": ", ".join(pr["files"]),
        "{{A vs B}}": "Session narrative versus repository/API/runtime evidence",
        "{{E-IDs}}": "E-001 E-002",
        "{{Code/runtime/spec/owner}}": "Repository history, current code, and reproducible test behavior",
        "{{Resolution rationale}}": "Session narratives are discovery leads; repository state, official documentation, and reproducible runtime evidence prevail.",
        "{{Boundary}}": "Final exact-head verification, base comparison where applicable, and human public-summary audit remain independently gated.",
        "{{What is current and independently proven against the exact head.}}":
            "GitHub identity, head/base/merge-base, changed files, commits, checks/reviews snapshot, artifact matches, and primary session lineage are captured in E-001 and E-002.",
        "{{Required work, failed/stale checks, open review threads, missing docs, or None with evidence.}}":
            "This remains a draft: independently recapture base-fails/head-passes logs and reconcile every current check and review thread before acceptance.",
        "{{Single concrete action, owner, trigger, and validation.}}":
            "Report author: capture immutable base/head test evidence at the current SHA, then rerun validation and review the public summary.",
        "{{PR}}": f'#{pr["number"]}',
        "{{SHA}}": pr["head_sha"][:12],
        "{{ISO-8601}}": pr["updated_at"],
    }
    for old, new in replacements.items():
        source = source.replace(old, esc(new))

    scope = replacements["{{Scope of this artifact — what it covers and what it deliberately does not.}}"]
    source = re.sub(
        r'(<div class="scope">).*?(<code>)',
        lambda match: match.group(1) + esc(scope) + match.group(2),
        source,
        count=1,
        flags=re.S,
    )

    source = re.sub(r'\{\{([^{}]+)\}\}', lambda match: unknown_for(match.group(1)), source)
    source = unseal_report(source)
    args.report.write_text(source)
    print(args.report.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
