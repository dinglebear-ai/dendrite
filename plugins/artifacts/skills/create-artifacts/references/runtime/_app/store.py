"""Thread-safe cached catalog with portable filesystem change watching."""
from __future__ import annotations
import threading
import time
from pathlib import Path
from .catalog import load_catalog

class CatalogStore:
    def __init__(self, root: Path, interval: float = 1.0):
        self.root, self.interval = root, interval
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._catalog = load_catalog(root)
        self._stamp = self._filesystem_stamp()
        self._running = False

    def _filesystem_stamp(self):
        values = []
        for path in self.root.iterdir():
            if path.name in {".git", "index.html", "__pycache__"}:
                continue
            if path.is_dir() and path.name.startswith("_") and path.name not in {"_app"}:
                continue
            paths = path.rglob("*") if path.is_dir() else (path,)
            for child in paths:
                if child.is_file() and "__pycache__" not in child.parts:
                    stat = child.stat()
                    values.append((str(child), stat.st_mtime_ns, stat.st_size))
        return hash(tuple(values))

    def get(self):
        with self._lock:
            return self._catalog

    def refresh(self, force=False):
        stamp = self._filesystem_stamp()
        with self._lock:
            if not force and stamp == self._stamp:
                return False
        catalog = load_catalog(self.root)
        with self._changed:
            self._catalog, self._stamp = catalog, stamp
            self._changed.notify_all()
        return True

    def wait_for_change(self, signature, timeout=25):
        with self._changed:
            if self._catalog["signature"] == signature:
                self._changed.wait(timeout)
            return self._catalog

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._watch, name="artifact-watch", daemon=True).start()

    def stop(self):
        self._running = False

    def _watch(self):
        while self._running:
            try:
                self.refresh()
            except OSError:
                pass
            time.sleep(self.interval)
