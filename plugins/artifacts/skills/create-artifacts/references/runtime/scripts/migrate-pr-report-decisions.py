#!/usr/bin/env python3
"""Replace legacy commit-as-decision tables with reviewer-oriented decision cards."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


def card(identifier: str, title: str, choice: str, alternatives: str,
         consequences: str, falsifier: str, evidence: str) -> str:
    return (
        f'<article class="decision-card" data-record-id="{identifier}" data-state="PASS" data-ref-ids="E-001">'
        f'<header><span class="decision-id">{identifier}</span><h4 class="decision-title">{title}</h4>'
        '<span class="decision-state">SUPPORTED</span></header><div class="decision-body">'
        f'<div class="decision-choice"><span class="label">Chosen direction and why</span><p>{choice}</p></div>'
        f'<div class="decision-facts"><div class="decision-fact"><span class="label">Alternatives</span>{alternatives}</div>'
        f'<div class="decision-fact"><span class="label">Consequences / rollback</span>{consequences}</div>'
        f'<div class="decision-fact"><span class="label">What would change this</span>{falsifier}</div></div></div>'
        f'<footer class="decision-evidence"><span class="label">Evidence</span><code>{evidence}</code></footer></article>'
    )


REMOTE_SHARE_DECISIONS = [
    ("DEC-001", "Build remote shares on the existing local-mount lifecycle",
     "Extend the Unassigned Devices lifecycle introduced by the stacked base instead of creating a parallel remote-only orchestration path. This keeps mount ownership, state transitions, and cleanup in one storage boundary.",
     "A separate remote-share service or direct command execution from callers would duplicate lifecycle policy and split ownership.",
     "The remote feature remains coupled to the stacked base. Roll back the remote-share commits without removing the local mount lifecycle.",
     "Repository evidence showing that the base lifecycle cannot represent remote effects, or reproducible behavior proving the shared boundary breaks isolation.",
     "E-001 · c2ac8c3c · stacked base 0a7ae44a"),
    ("DEC-002", "Treat successful commands as insufficient proof of mount state",
     "Fail closed unless the observable mount state agrees with the requested transition. A zero exit status alone does not prove that the share is mounted, unmounted, or safe to persist.",
     "Trusting command exit status is simpler but permits false success when the host state diverges. Optimistic persistence would make that divergence durable.",
     "Failures surface earlier and may reject ambiguous host behavior. Rollback is a localized return to exit-status-only handling, with the associated integrity risk.",
     "A documented platform contract and repeated runtime evidence proving the command result is an authoritative mount-state oracle in every supported environment.",
     "E-001 · 8a0c96a1 · 215269c9"),
    ("DEC-003", "Serialize lifecycle effects and bind them to durable intent",
     "Order remote mount effects so concurrent requests cannot race past one another, and preserve enough intent to recover consistently across partial failures.",
     "Uncoordinated effects maximize throughput but permit stale writers and overlapping mount operations. Process-local ordering without durable intent does not cover recovery.",
     "Serialization narrows concurrency and adds recovery bookkeeping. The commits are independently revertible if measurements prove the ordering cost is material.",
     "A reproducible concurrency model that maintains the same invariants without serialization, supported by race and recovery tests.",
     "E-001 · 1a4de3fd · 4c0b5f63 · 608adc32 · adc8aa15 · 8261ac2b"),
    ("DEC-004", "Keep credentials durable without making plaintext configuration authoritative",
     "Route remote credentials through the repository credential boundary and authenticate their durable representation, while keeping share configuration and secret material conceptually separate.",
     "Plaintext configuration is easier to inspect but expands disclosure risk. Ephemeral-only credentials avoid persistence but cannot support durable remount and recovery intent.",
     "The credential store becomes part of the remote-share availability path. Rollback removes durable remote authentication and therefore the recovery capability that depends on it.",
     "Official platform guidance requiring a different secret authority, or reproducible evidence that the selected durable representation cannot preserve confidentiality and integrity.",
     "E-001 · e8b0c7dd · 608adc32"),
]


def migrate(path: Path) -> None:
    source = path.read_text()
    match = re.search(r'(<details id="decisions".*?</summary>).*?</details>', source, re.S)
    if not match:
        raise SystemExit(f"missing decisions section: {path}")
    if "class=\"decision-stack\"" in match.group(0):
        source = source.replace("Decision and alternative ledger", "Material decisions and alternatives", 1)
        source = source.replace(
            "Reviewable rationale—not hidden chain-of-thought—for every material design, scope, testing, and release choice.",
            "The small set of choices that shaped the PR, with reviewable rationale and explicit reversal conditions.",
            1,
        )
        path.write_text(source)
        return
    if "add unassigned remote shares" not in match.group(0):
        raise SystemExit("legacy section is not a recognized report; regenerate it with seed-pr-report.py")
    cards = "".join(card(*item) for item in REMOTE_SHARE_DECISIONS)
    heading = match.group(1).replace(
        "Decision and alternative ledger",
        "Material decisions and alternatives",
    ).replace(
        "Reviewable rationale—not hidden chain-of-thought—for every material design, scope, testing, and release choice.",
        "The small set of choices that shaped the PR, with reviewable rationale and explicit reversal conditions.",
    )
    detail = (
        '<div class="detail full"><div><div class="decision-intro"><div><h4>Reviewer decision map</h4>'
        '<p>Four material architectural choices reconstructed from the reviewed commit series. Forecast, review-marker, and merge commits remain chronology—not decisions.</p></div>'
        '<div class="decision-denominator">4 material decisions<br>E-001 · authoritative commit series</div></div>'
        f'<div class="decision-stack">{cards}</div><div class="limit">The cards expose attributable engineering rationale, tradeoffs, and falsifiers; they do not claim hidden agent chain-of-thought.</div></div></div>'
    )
    updated = source[:match.start()] + heading + detail + "</details>" + source[match.end():]
    path.write_text(updated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    migrate(args.report.resolve())


if __name__ == "__main__":
    main()
