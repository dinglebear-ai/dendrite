#!/usr/bin/env python3
"""Recoverably stage and validate report/evidence files, then commit with rollback."""
from __future__ import annotations
import argparse, hashlib, html, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from _app.pr_manifest import locked, package_locked
from _app.pr_seal import seal_locked, verify_locked
def set_meta(source,name,value):
    return re.sub(r'(<meta name="artifact\.'+re.escape(name)+r'" content=")[^"]*(">)',lambda m:m.group(1)+html.escape(str(value),quote=True)+m.group(2),source,count=1)
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("report",type=Path); p.add_argument("--root",type=Path)
    p.add_argument("--current-head",required=True); p.add_argument("--current-merge-base",required=True); p.add_argument("--changed-files",type=Path,required=True); a=p.parse_args()
    report=a.report.resolve(); original=report.read_text(); found=re.search(r'<meta name="artifact\.evidence-manifest" content="([^"]*)">',original)
    if not found: p.error("missing evidence manifest")
    manifest=Path(html.unescape(found.group(1))); descriptor,name=tempfile.mkstemp(prefix=report.stem+"--candidate-",suffix=".html",dir=report.parent); os.close(descriptor); candidate=Path(name)
    staged_manifest=manifest.with_name(manifest.name+".candidate"); backup=manifest.with_name(manifest.name+".pre-finalize")
    if staged_manifest.exists() or backup.exists(): p.error("unfinished finalization files exist; inspect and recover first")
    committed_manifest=False; committed_digest=None
    initial_manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    try:
        with locked(manifest):
            candidate.write_text(set_meta(original,"evidence-manifest",staged_manifest)); shutil.copy2(manifest,staged_manifest)
        if subprocess.run([sys.executable,str(Path(__file__).with_name("update-pr-report.py")),str(candidate)],check=False).returncode: return 1
        if subprocess.run([sys.executable,str(Path(__file__).with_name("sync-pr-report-ledgers.py")),str(candidate)],check=False).returncode: return 1
        source=set_meta(candidate.read_text(),"status","accepted"); source=set_meta(source,"evidence-manifest",manifest); candidate.write_text(source)
        validation_source=set_meta(candidate.read_text(),"evidence-manifest",staged_manifest); candidate.write_text(validation_source)
        validate_command=[sys.executable,str(Path(__file__).with_name("validate-pr-report.py")),str(candidate),"--canonical-path",str(report),"--allow-unsealed","--current-head",a.current_head,"--current-merge-base",a.current_merge_base,"--changed-files",str(a.changed_files)]
        if a.root: validate_command += ["--root",str(a.root)]
        if subprocess.run(validate_command,check=False).returncode: return 1
        candidate.write_text(set_meta(candidate.read_text(),"evidence-manifest",manifest))
        with package_locked(report):
            with locked(manifest):
                if hashlib.sha256(manifest.read_bytes()).hexdigest()!=initial_manifest_digest: return 1
                os.replace(manifest,backup); os.replace(staged_manifest,manifest); committed_manifest=True; committed_digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
                seal_locked(candidate,manifest)
                if not verify_locked(candidate,manifest): return 1
                os.chmod(candidate,report.stat().st_mode); os.replace(candidate,report)
                committed_manifest=False; backup.unlink(missing_ok=True); return 0
    finally:
        if committed_manifest and backup.exists():
            with package_locked(report):
                with locked(manifest):
                    if hashlib.sha256(manifest.read_bytes()).hexdigest()==committed_digest:
                        manifest.unlink(missing_ok=True); os.replace(backup,manifest)
        candidate.unlink(missing_ok=True); staged_manifest.unlink(missing_ok=True)
if __name__=="__main__": raise SystemExit(main())
