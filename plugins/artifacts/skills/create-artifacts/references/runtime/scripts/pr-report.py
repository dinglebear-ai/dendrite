#!/usr/bin/env python3
"""One entry point for PR-report creation, evidence, drift, review, and export."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from _app.pr_manifest import package_locked  # noqa: E402
from _app.pr_report_system import (  # noqa: E402
    build_manifest, canonical_json, detect_drift, embed_manifest, public_summary,
    scan_public, semantic_diff, semantic_snapshot,
)


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def run_script(name: str, args: list[str]) -> int:
    return subprocess.run([sys.executable, str(Path(__file__).with_name(name)), *args], check=False).returncode


def compile_report(report: Path, output: Path | None = None) -> dict:
    manifest = build_manifest(report)
    target = output or report
    source = embed_manifest(report.read_text(), manifest)
    with package_locked(target):
        descriptor, temporary_name = tempfile.mkstemp(prefix=target.stem + "--", suffix=".html", dir=target.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            temporary.write_text(source)
            os.chmod(temporary, report.stat().st_mode)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return manifest


def bundle(report: Path, output: Path) -> dict:
    manifest = build_manifest(report)
    if output.exists():
        raise SystemExit(f"refusing to overwrite evidence bundle: {output}")
    output.mkdir(parents=True)
    copied = []
    shutil.copy2(report, output / report.name)
    copied.append(output / report.name)
    for record in manifest["evidence"]:
        source = Path(record["path"])
        if source.is_file():
            target = output / "evidence" / record["id"] / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target)
    bundle_manifest = {
        "schema": 1,
        "source_report": str(report.resolve()),
        "files": [{"path": path.relative_to(output).as_posix(),
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "bytes": path.stat().st_size} for path in copied],
        "report_manifest": manifest,
    }
    bundle_manifest["bundle_sha256"] = hashlib.sha256(canonical_json(bundle_manifest).encode()).hexdigest()
    output.joinpath("manifest.json").write_text(json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n")
    return bundle_manifest


def export_public(report: Path, output: Path) -> dict:
    block = public_summary(report.read_text())
    findings = scan_public(block)
    if findings:
        emit({"status": "BLOCKED", "findings": findings})
        raise SystemExit(1)
    document = """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"robots\" content=\"noindex,nofollow\"><title>PR public summary candidate</title><style>body{font:16px/1.55 system-ui;max-width:860px;margin:48px auto;padding:0 24px;color:#111;background:#fff}summary{font-weight:700}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px;text-align:left}.limit{border-left:4px solid #f60;padding:12px;margin-top:16px}</style></head><body>""" + block + "<p class=\"limit\"><strong>Publication boundary:</strong> This generated candidate passed local pattern scanning. It is not publication authorization and still requires a human destination-and-payload audit.</p></body></html>"
    if output.exists():
        raise SystemExit(f"refusing to overwrite public export: {output}")
    output.write_text(document)
    return {"status": "PASS", "output": str(output.resolve()),
            "sha256": hashlib.sha256(document.encode()).hexdigest(), "scanner_findings": 0}


def main() -> int:
    passthrough = {
        "discover": "generate-pr-report-draft.py", "create": "new-pr-report.py",
        "refresh": "update-pr-report.py", "seal": "seal-pr-report.py",
        "watch-evidence": "capture-cortex-evidence-stream.py",
    }
    if len(sys.argv) > 1 and sys.argv[1] in passthrough:
        child_args = sys.argv[2:]
        if child_args[:1] == ["--"]:
            child_args = child_args[1:]
        return run_script(passthrough[sys.argv[1]], child_args)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("manifest", "compile", "readiness", "validate", "audit-accessibility"):
        command = sub.add_parser(name); command.add_argument("report", type=Path)
        if name == "manifest": command.add_argument("--output", type=Path)
    drift = sub.add_parser("drift"); drift.add_argument("report", type=Path)
    drift.add_argument("--head"); drift.add_argument("--merge-base"); drift.add_argument("--changed-files", type=Path)
    diff = sub.add_parser("diff"); diff.add_argument("before", type=Path); diff.add_argument("after", type=Path)
    package = sub.add_parser("bundle"); package.add_argument("report", type=Path); package.add_argument("output", type=Path)
    public = sub.add_parser("export-public"); public.add_argument("report", type=Path); public.add_argument("output", type=Path)
    acknowledge = sub.add_parser("acknowledge"); acknowledge.add_argument("report", type=Path)
    acknowledge.add_argument("checkpoint", choices=["problem","scope","architecture","tests","security-privacy","operations","documentation","public-summary"])
    acknowledge.add_argument("--reviewer", required=True); acknowledge.add_argument("--note", default="")
    args = parser.parse_args()
    if args.command in {"manifest", "compile", "readiness", "validate", "audit-accessibility"}:
        manifest = build_manifest(args.report.resolve())
        if args.command == "compile":
            manifest = compile_report(args.report.resolve())
        if args.command == "manifest" and args.output:
            args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        if args.command == "readiness":
            emit(manifest["readiness"]); return 0
        if args.command == "validate":
            issues = manifest["graph_issues"]
            emit({"status": "PASS" if not any(issues.values()) else "FAIL", "issues": issues})
            return 1 if any(issues.values()) else 0
        if args.command == "audit-accessibility":
            source=args.report.read_text(); checks={
                "document_language":'<html lang="en">' in source,
                "viewport":'name="viewport"' in source,
                "keyboard_focus":':focus-visible' in source,
                "reduced_motion":'prefers-reduced-motion' in source,
                "forced_colors":'forced-colors:active' in source,
                "live_status":'aria-live="polite"' in source,
                "table_captions":source.count('<table class="ledger">')==source.count('<caption>'),
                "navigation_label":'aria-label="PR report stages"' in source,
            }; emit({"status":"PASS" if all(checks.values()) else "FAIL","checks":checks})
            return 0 if all(checks.values()) else 1
        emit(manifest); return 0
    if args.command == "drift":
        digest = hashlib.sha256(args.changed_files.read_bytes()).hexdigest() if args.changed_files else None
        result = detect_drift(build_manifest(args.report.resolve()), head=args.head,
                              merge_base=args.merge_base, changed_files_digest=digest)
        emit({"status": "STALE" if result.stale else "CURRENT", "stale": result.stale,
              "observed": result.observed}); return 1 if result.stale else 0
    if args.command == "diff":
        emit(semantic_diff(semantic_snapshot(build_manifest(args.before.resolve())),
                           semantic_snapshot(build_manifest(args.after.resolve())))); return 0
    if args.command == "bundle":
        emit(bundle(args.report.resolve(), args.output.resolve())); return 0
    if args.command == "export-public":
        emit(export_public(args.report.resolve(), args.output.resolve())); return 0
    if args.command == "acknowledge":
        report = args.report.resolve(); manifest = build_manifest(report)
        record = {"checkpoint":args.checkpoint,"reviewer":args.reviewer,"note":args.note,
                  "acknowledged_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "head_sha":manifest["identity"].get("head","").split("@")[-1].strip(),
                  "report_sha256":manifest["report_sha256"]}
        target=report.with_suffix(".review.jsonl")
        with target.open("a") as handle: handle.write(canonical_json(record)+"\n")
        emit(record); return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
