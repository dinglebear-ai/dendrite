"""Internal report sealing primitives; callers must hold the manifest lock."""
from __future__ import annotations
import hashlib, os, re, tempfile
from pathlib import Path
REPORT=re.compile(r'(<meta name="artifact\.report-digest" content=")[^"]*(">)')
MANIFEST=re.compile(r'(<meta name="artifact\.evidence-manifest-digest" content=")[^"]*(">)')
def replace(pattern,source,value):
    updated,count=pattern.subn(lambda m:m.group(1)+value+m.group(2),source,count=1)
    if count!=1: raise ValueError("missing required digest metadata")
    return updated
def report_digest(source): return hashlib.sha256(replace(REPORT,source,"UNSEALED").encode()).hexdigest()
def seal_locked(report:Path,manifest:Path,source:str|None=None):
    source=report.read_text() if source is None else source; manifest_digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    source=replace(MANIFEST,source,manifest_digest); source=replace(REPORT,source,report_digest(source))
    descriptor,temporary=tempfile.mkstemp(prefix=report.name+".",dir=report.parent)
    try:
        with os.fdopen(descriptor,"w",encoding="utf-8") as handle: handle.write(source); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary,report)
    finally: Path(temporary).unlink(missing_ok=True)
def verify_locked(report:Path,manifest:Path):
    source=report.read_text(); md=hashlib.sha256(manifest.read_bytes()).hexdigest()
    current_m=re.search(r'<meta name="artifact\.evidence-manifest-digest" content="([^"]*)">',source)
    current_r=re.search(r'<meta name="artifact\.report-digest" content="([^"]*)">',source)
    return bool(current_m and current_r and current_m.group(1)==md and current_r.group(1)==report_digest(source))
