"""Shared evidence-manifest locking; every reader/writer coordinates here."""
from __future__ import annotations
import fcntl
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def locked(manifest: Path):
    lock_path = manifest.with_suffix(manifest.suffix + ".lock")
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

@contextmanager
def package_locked(report: Path):
    """Serialize report-byte replacement across update, sync, seal, and finalize."""
    with report.with_suffix(report.suffix + ".package.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
