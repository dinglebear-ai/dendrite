#!/usr/bin/env python3
"""Apply a reviewed lifecycle dossier to PR-report section states and bodies."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from pathlib import Path


VALID_STATES = {"PASS", "FAIL", "BLOCKED", "STALE", "NOT RUN", "UNKNOWN", "NOT APPLICABLE"}


def replace_opening(source: str, section_id: str, state: str, reason: str, refs: list[str]) -> str:
    pattern = rf'<details id="{re.escape(section_id)}"[^>]*>'
    match = re.search(pattern, source)
    if not match:
        raise ValueError(f"report has no section {section_id}")
    opening = match.group(0)
    opening = re.sub(r'\sdata-(?:state|reason|ref-ids|rule)="[^"]*"', "", opening)
    attributes = (f' data-state="{html.escape(state, quote=True)}"'
                  f' data-reason="{html.escape(reason, quote=True)}"'
                  f' data-ref-ids="{html.escape(" ".join(refs), quote=True)}"')
    return source[:match.start()] + opening[:-1] + attributes + ">" + source[match.end():]


def replace_body(source: str, section_id: str, body: str) -> str:
    return re.sub(
        rf'(<details id="{re.escape(section_id)}"[^>]*>.*?</summary>).*?</details>',
        lambda match: match.group(1) + body + "</details>", source, count=1, flags=re.S)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("dossier", type=Path)
    args = parser.parse_args()
    dossier = json.loads(args.dossier.read_text())
    source = args.report.read_text()
    evidence = set(dossier["evidence_ids"])
    for section_id, entry in dossier["sections"].items():
        state = entry["state"]
        refs = entry.get("refs", [])
        reason = entry["reason"]
        if state not in VALID_STATES:
            raise ValueError(f"invalid state for {section_id}: {state}")
        if any(ref not in evidence for ref in refs):
            raise ValueError(f"unknown evidence reference in {section_id}")
        if state != "PASS" and not reason.strip():
            raise ValueError(f"non-PASS section {section_id} requires a reason")
        source = replace_opening(source, section_id, state, reason, refs)
        if state == "NOT APPLICABLE":
            rule = entry.get("rule", "").strip()
            if not rule:
                raise ValueError(f"NOT APPLICABLE section {section_id} requires a rule")
            source = source.replace(
                f'<details id="{section_id}"',
                f'<details id="{section_id}" data-rule="{html.escape(rule, quote=True)}"', 1)
        if entry.get("body"):
            source = replace_body(source, section_id, entry["body"])
    descriptor, temporary_name = tempfile.mkstemp(prefix=args.report.stem + "--", suffix=".html", dir=args.report.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(source)
        os.chmod(temporary, args.report.stat().st_mode)
        os.replace(temporary, args.report)
    finally:
        temporary.unlink(missing_ok=True)
    print(args.report.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
