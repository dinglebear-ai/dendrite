#!/usr/bin/env python3
"""Fail-closed CLI to validate, seal, or verify a PR report and manifest."""
from __future__ import annotations
import argparse, html, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from _app.pr_manifest import locked, package_locked
from _app.pr_seal import seal_locked, verify_locked
def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("report",type=Path); parser.add_argument("--verify",action="store_true")
    parser.add_argument("--root",type=Path); parser.add_argument("--current-head"); parser.add_argument("--current-merge-base"); parser.add_argument("--changed-files",type=Path)
    args=parser.parse_args(); report=args.report.resolve(); source=report.read_text(); found=re.search(r'<meta name="artifact\.evidence-manifest" content="([^"]*)">',source)
    if not found: parser.error("report has no evidence manifest")
    manifest=Path(html.unescape(found.group(1)))
    if args.verify:
        with locked(manifest): passed=verify_locked(report,manifest)
        print("PASS" if passed else "FAIL", "report and evidence-manifest seals"); return 0 if passed else 1
    validated_report_generation=__import__("hashlib").sha256(source.encode()).hexdigest()
    with locked(manifest): validated_generation=__import__("hashlib").sha256(manifest.read_bytes()).hexdigest()
    command=[sys.executable,str(Path(__file__).with_name("validate-pr-report.py")),str(report),"--allow-unsealed"]
    if args.root: command += ["--root",str(args.root)]
    for flag,value in (("--current-head",args.current_head),("--current-merge-base",args.current_merge_base),("--changed-files",args.changed_files)):
        if value: command += [flag,str(value)]
    if subprocess.run(command,check=False).returncode: return 1
    with package_locked(report):
        with locked(manifest):
            if (__import__("hashlib").sha256(manifest.read_bytes()).hexdigest()!=validated_generation or
                    __import__("hashlib").sha256(report.read_bytes()).hexdigest()!=validated_report_generation):
                print("FAIL report or evidence manifest changed after validation"); return 1
            seal_locked(report,manifest,source)
    print("PASS sealed"); return 0
if __name__=="__main__": raise SystemExit(main())
