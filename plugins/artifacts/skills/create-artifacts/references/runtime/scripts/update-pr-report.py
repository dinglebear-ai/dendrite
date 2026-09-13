#!/usr/bin/env python3
"""Refresh mutable Git metadata, revision, staleness, and integrity fields."""
from __future__ import annotations
import argparse, hashlib, html, json, os, re, subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from _app.pr_manifest import locked, package_locked

def git(root, *argv): return subprocess.run(["git", "-C", str(root), *argv], text=True, capture_output=True, check=True).stdout.strip()
def set_meta(source, name, value):
    return re.sub(r'(<meta name="artifact\.' + re.escape(name) + r'" content=")[^"]*(">)', lambda m: m.group(1)+html.escape(value, quote=True)+m.group(2), source, count=1)
def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("report", type=Path)
    parser.add_argument("--offline", action="store_true", help="Advance report revision without claiming mutable Git/GitHub refresh")
    args=parser.parse_args()
    source=args.report.read_text(); meta=dict(re.findall(r'<meta name="artifact\.([\w-]+)" content="([^"]*)">', source))
    root=Path(html.unescape(meta["worktree"])).resolve()
    if not args.offline and Path(git(root,"rev-parse","--show-toplevel")).resolve()!=root: raise ValueError("worktree is not physical repository root")
    if args.offline:
        branch=html.unescape(meta["branch"]); head=html.unescape(meta["target"])
        merge=html.unescape(meta["merge-base"])
    else:
        branch=git(root,"branch","--show-current"); head=git(root,"rev-parse","HEAD")
    target_remote=None
    for candidate_remote in ([] if args.offline else git(root,"remote").splitlines()):
        remote=git(root,"remote","get-url",candidate_remote); match=re.fullmatch(r'(?:git@github\.com:|https?://github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?',remote,re.I)
        if match and (match.group(1)+"/"+match.group(2)).lower()==html.unescape(meta["repository"]).lower(): target_remote=candidate_remote; break
    if not args.offline and not target_remote: raise ValueError("no remote matches target repository")
    if not args.offline and branch != html.unescape(meta.get("branch", "")): raise ValueError("live branch differs from report branch; explicit migration required")
    base_ref,base=(part.strip() for part in html.unescape(meta["base"]).rsplit("@",1))
    resolved=None
    for ref in (() if args.offline else (target_remote+"/"+base_ref,base_ref)):
        try: resolved=git(root,"rev-parse","--verify",ref); break
        except subprocess.CalledProcessError: pass
    if not args.offline and (resolved is None or resolved.lower()!=base.lower()): raise ValueError("declared base ref does not resolve to recorded SHA")
    if not args.offline: merge=git(root,"merge-base",base,head)
    prior=hashlib.sha256(re.sub(r'(<meta name="artifact\.report-digest" content=")[^"]*(">)',r'\1UNSEALED\2',source,count=1).encode()).hexdigest()
    revision=str(int(meta.get("revision","1"))+1); now=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    for name,value in (("branch",branch),("head",branch+" @ "+head),("target",head),("merge-base",merge),("updated",now),("revision",revision),("report-digest","UNSEALED"),("evidence-manifest-digest","UNSEALED"),("provenance-status","VERIFIED")):
        source=set_meta(source,name,value)
    def stale_tag(match):
        tag=match.group(0); sha=re.search(r'data-source-sha="([0-9a-f]{40})"',tag,re.I)
        if sha and sha.group(1).lower()!=head.lower() and 'data-state="PASS"' in tag:
            tag=tag.replace('data-state="PASS"','data-state="STALE"')
            if 'data-reason=' not in tag: tag=tag[:-1]+' data-reason="source head changed">'
        return tag
    source=re.sub(r'<[^>]+data-source-sha="[0-9a-f]{40}"[^>]*>',stale_tag,source,flags=re.I)
    manifest=Path(html.unescape(meta["evidence-manifest"]))
    with locked(manifest):
        records=[json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
        for record in records:
            if record.get("applies_to")=="head" and record.get("source_sha")!=head.lower():
                record["state"]="STALE"; record["reason"]="source head changed"
        descriptor,manifest_tmp=tempfile.mkstemp(prefix=manifest.name+".",dir=manifest.parent)
        try:
            with os.fdopen(descriptor,"w",encoding="utf-8") as handle:
                handle.write("".join(json.dumps(row,sort_keys=True)+"\n" for row in records)); handle.flush(); os.fsync(handle.fileno())
            os.replace(manifest_tmp,manifest)
        finally: Path(manifest_tmp).unlink(missing_ok=True)
    marker='<!-- revision-ledger:rows -->'; reason="offline evidence enrichment; mutable identity not refreshed" if args.offline else "live refresh"
    row=f'<tr><td>{revision}</td><td>{now}</td><td>{head}</td><td>lifecycle evidence and report state</td><td>{reason}</td><td>{prior}</td></tr>'
    if marker in source: source=source.replace(marker,marker+row,1)
    descriptor,temporary=tempfile.mkstemp(prefix=args.report.name+".",dir=args.report.parent)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8") as handle: handle.write(source); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary,args.report.stat().st_mode)
        with package_locked(args.report): os.replace(temporary,args.report)
    finally: Path(temporary).unlink(missing_ok=True)
    return 0
if __name__ == "__main__": raise SystemExit(main())
