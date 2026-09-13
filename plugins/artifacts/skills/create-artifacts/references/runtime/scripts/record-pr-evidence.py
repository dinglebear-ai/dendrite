#!/usr/bin/env python3
"""Hash an existing evidence file and append a stable record to a PR manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from _app.pr_manifest import locked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--id", required=True, help="Stable ID such as E-014")
    parser.add_argument("--kind", required=True)
    parser.add_argument("--evidence-type", default="immutable-snapshot", choices=(
        "immutable-snapshot", "reproducible-command", "human-observation",
        "inference", "live-reference", "unverified-assertion"))
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--producer", required=True, help="Agent, human, tool, or CI job")
    parser.add_argument("--command", required=True, help="Exact producing command or capture method")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--applies-to", required=True,
                        choices=("base", "head", "environment", "external"))
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--state", required=True)
    parser.add_argument("--reason", default="", help="Required for every non-PASS state")
    args = parser.parse_args()
    if not args.cwd.is_absolute() or not args.cwd.is_dir():
        parser.error("--cwd must be an absolute existing directory")
    if not re.fullmatch(r"E-\d{3,}", args.id):
        parser.error("--id must match E-001")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.source_sha):
        parser.error("--source-sha must be a full SHA")
    states = {"PASS", "FAIL", "BLOCKED", "NOT RUN", "NOT APPLICABLE", "UNKNOWN", "STALE"}
    if args.state not in states:
        parser.error("--state is not in the PR report state vocabulary")
    if args.state != "PASS" and not args.reason.strip():
        parser.error("--reason is required for every non-PASS state")
    path = args.file.resolve()
    if not path.is_file():
        parser.error("--file must exist")
    manifest = args.manifest.resolve()
    if path == manifest:
        parser.error("the manifest cannot be recorded as its own evidence file")
    record = {
        "id": args.id, "kind": args.kind, "evidence_type": args.evidence_type, "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
        "producer": args.producer, "command": args.command, "cwd": str(args.cwd.resolve()),
        "source_sha": args.source_sha.lower(), "state": args.state,
        "applies_to": args.applies_to,
        "reason": args.reason,
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    if not manifest.is_file():
        parser.error("--manifest must already exist")
    with locked(manifest):
        try:
            records = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            parser.error("existing manifest is malformed: " + str(error))
        if any(existing.get("id") == args.id for existing in records):
            parser.error("evidence ID already exists")
        with manifest.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n"); handle.flush()
            __import__("os").fsync(handle.fileno())
    print(args.id, record["sha256"], path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
