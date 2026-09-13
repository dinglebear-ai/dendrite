#!/usr/bin/env python3
"""Export a portable static snapshot using the live app's shared renderer."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from _app.catalog import load_catalog  # noqa: E402
from _app.render import render_index  # noqa: E402

def main():
    import subprocess
    from _app.projects import SKILL
    return subprocess.call([sys.executable,str(SKILL/'scripts/artifacts.py'),'index',*sys.argv[1:]])

if __name__ == "__main__": raise SystemExit(main())
