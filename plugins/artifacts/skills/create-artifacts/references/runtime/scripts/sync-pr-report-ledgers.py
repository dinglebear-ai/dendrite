#!/usr/bin/env python3
"""Atomically render complete evidence JSONL records into the HTML ledger."""
from __future__ import annotations
import argparse, hashlib, html, json, os, re, tempfile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from _app.pr_manifest import locked, package_locked
BLOCK = re.compile(r'(<!-- evidence-ledger:begin -->).*?(<!-- evidence-ledger:end -->)', re.S)
FIELDS = ("id", "kind", "path", "sha256", "bytes", "producer", "command", "cwd",
          "source_sha", "applies_to", "state", "reason", "captured_at")
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("report",type=Path); a=p.parse_args()
    source=a.report.read_text(); found=re.search(r'<meta name="artifact\.evidence-manifest" content="([^"]*)">',source)
    if not found: p.error("missing manifest metadata")
    manifest=Path(html.unescape(found.group(1)))
    with locked(manifest):
        records=[json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
    rows=[]
    for record in records:
        missing=set(FIELDS)-set(record)
        if missing: p.error("manifest record missing " + ", ".join(sorted(missing)))
        cells="".join("<td>{}</td>".format(html.escape(str(record[field]))) for field in FIELDS)
        record_digest=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        rows.append('<tr data-record-id="{}" data-record-digest="{}" data-state="{}" data-reason="{}">{}</tr>'.format(
            html.escape(str(record["id"])),record_digest,html.escape(str(record["state"])),
            html.escape(str(record["reason"] or "None")),cells))
    headings="".join("<th>{}</th>".format(html.escape(field)) for field in FIELDS)
    table="<table class=\"ledger\"><caption>Complete synchronized evidence manifest records.</caption><tr>"+headings+"</tr>"+"".join(rows)+"</table>"
    updated,count=BLOCK.subn(lambda m:m.group(1)+table+m.group(2),source,count=1)
    if count!=1: p.error("missing evidence ledger markers")
    updated=re.sub(r'(<meta name="artifact\.(?:report-digest|evidence-manifest-digest)" content=")[^"]*(">)',r'\1UNSEALED\2',updated)
    descriptor,temporary=tempfile.mkstemp(prefix=a.report.name+".",dir=a.report.parent)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8") as handle: handle.write(updated); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary,a.report.stat().st_mode)
        with package_locked(a.report): os.replace(temporary,a.report)
    finally: Path(temporary).unlink(missing_ok=True)
    return 0
if __name__=="__main__": raise SystemExit(main())
