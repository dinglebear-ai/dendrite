#!/usr/bin/env python3
"""Run an argv command without a shell and atomically capture reproducible evidence."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

SENSITIVE = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "COOKIE", "AUTH", "KEY")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--id", required=True)
    parser.add_argument("--kind", required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-type", default="reproducible-command", choices=(
        "immutable-snapshot", "reproducible-command", "human-observation",
        "inference", "live-reference", "unverified-assertion"))
    parser.add_argument("--producer", required=True); parser.add_argument("--source-sha", required=True)
    parser.add_argument("--applies-to", choices=("base", "head", "environment", "external"), required=True)
    parser.add_argument("--cwd", type=Path, required=True); parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--expected-exit", type=int, default=0,
                        help="Expected observed exit code; base-fails proof commonly uses nonzero")
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(); argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not argv: parser.error("a command is required after --")
    if args.output.exists(): parser.error("--output already exists; evidence capture is immutable")
    if not args.manifest.is_file(): parser.error("--manifest must exist")
    try:
        existing = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    except json.JSONDecodeError as error: parser.error("existing manifest is malformed: " + str(error))
    if any(row.get("id") == args.id for row in existing): parser.error("evidence ID already exists")
    if not args.cwd.is_absolute(): parser.error("--cwd must be absolute")
    if any(any(word in name.upper() for word in SENSITIVE) for name in args.env):
        parser.error("refusing a potentially sensitive environment variable name")
    started = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"); before = time.monotonic()
    result = subprocess.run(argv, cwd=args.cwd, text=True, capture_output=True, shell=False, check=False)
    payload = {"argv": argv, "cwd": str(args.cwd), "started_at": started,
               "duration_seconds": round(time.monotonic() - before, 6), "exit_code": result.returncode,
               "expected_exit_code": args.expected_exit,
               "stdout": result.stdout, "stderr": result.stderr,
               "environment": {name: os.environ.get(name, "<unset>") for name in args.env}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=args.output.name + ".", dir=args.output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        try:
            os.link(temporary, args.output)  # atomic no-overwrite publication
        except FileExistsError:
            parser.error("--output was created concurrently; refusing overwrite")
    finally: Path(temporary).unlink(missing_ok=True)
    state = "PASS" if result.returncode == args.expected_exit else "FAIL"
    record = [sys.executable, str(Path(__file__).with_name("record-pr-evidence.py")),
              "--manifest", str(args.manifest), "--id", args.id, "--kind", args.kind,
              "--evidence-type", args.evidence_type,
              "--file", str(args.output), "--producer", args.producer, "--command", json.dumps(argv),
              "--source-sha", args.source_sha, "--cwd", str(args.cwd), "--applies-to", args.applies_to,
              "--state", state]
    if state != "PASS": record += ["--reason", "observed exit did not match expected exit"]
    if subprocess.run(record, check=False).returncode:
        args.output.unlink(missing_ok=True); return 2
    return 0 if result.returncode == args.expected_exit else 1

if __name__ == "__main__": raise SystemExit(main())
