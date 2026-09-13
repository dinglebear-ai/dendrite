#!/usr/bin/env python3
"""Capture a complete historical + bounded-live Cortex evidence bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


def append(path: Path, value: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def absolute_since(value: str) -> str:
    if value.endswith(("s", "m", "h", "d")) and value[:-1].isdigit():
        seconds = int(value[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[value[-1]]
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    return value


def event_position(payload: dict) -> int | None:
    event = payload.get("event")
    return event.get("id") if isinstance(event, dict) and isinstance(event.get("id"), int) else None


def stream_page(*, url: str, token: str, host_header: str | None, output: Path,
                history_limit: int, follow_deadline: float | None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
    if host_header:
        headers["Host"] = host_header
    request = urllib.request.Request(url, headers=headers)
    result = {"cursor": None, "events": 0, "evidence": 0, "snapshot": 0,
              "truncated": False, "caught_up": False}
    timeout = max(30, int(follow_deadline - time.monotonic() + 30)) if follow_deadline else 30
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        if content_type != "text/event-stream":
            raise RuntimeError(f"expected text/event-stream, received {content_type}")
        event, data = "message", []
        snapshot_high = historical_expected = None
        historical_seen = 0
        for raw in response:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith(":"):
                if follow_deadline is not None and time.monotonic() >= follow_deadline:
                    break
                continue
            if not line:
                if data:
                    payload = json.loads("\n".join(data))
                    append(output, {"record_type": event, "payload": payload})
                    result["events"] += 1
                    if event == "snapshot":
                        result["snapshot"] += 1
                        snapshot_high = payload.get("highWatermark")
                        historical_expected = payload.get("historicalCount", 0)
                        if historical_expected == 0:
                            result["caught_up"] = True
                    elif event == "evidence":
                        result["evidence"] += 1
                        historical_seen += 1
                        position = event_position(payload)
                        if historical_expected is not None and historical_seen >= historical_expected:
                            result["caught_up"] = (
                                historical_expected < history_limit
                                or (isinstance(position, int) and isinstance(snapshot_high, int)
                                    and position >= snapshot_high)
                            )
                    elif event == "history_truncated":
                        result["truncated"] = True
                    data = []
                    if result["truncated"]:
                        break
                    if result["caught_up"] and follow_deadline is None:
                        break
                event = "message"
                if follow_deadline is not None and time.monotonic() >= follow_deadline:
                    break
                continue
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("id:"):
                result["cursor"] = line[3:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
            if follow_deadline is not None and time.monotonic() >= follow_deadline:
                break
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--host-header", help="Explicit Host header for a trusted direct endpoint")
    parser.add_argument("--token-env", default="CORTEX_API_TOKEN")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--branch")
    scope.add_argument("--worktree")
    parser.add_argument("--since", default="7d")
    parser.add_argument("--kinds", default="")
    parser.add_argument("--history-limit", type=int, default=500)
    parser.add_argument("--follow-seconds", type=int, default=0)
    parser.add_argument("--cursor", help="Opaque resume cursor from a prior bundle footer")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        parser.error(f"{args.token_env} is not set")
    if args.output.exists():
        parser.error("refusing to overwrite an existing evidence stream")
    if not 1 <= args.history_limit <= 500:
        parser.error("--history-limit must be between 1 and 500")
    if args.follow_seconds < 0:
        parser.error("--follow-seconds must be non-negative")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    kinds = [item for item in args.kinds.split(",") if item]
    scope_value = ({"branch": args.branch} if args.branch else
                   {"worktree": str(Path(args.worktree).resolve())})
    query = {**scope_value, "since": absolute_since(args.since),
             "history_limit": args.history_limit, "include_payload": "true", "kinds": kinds}
    cursor = args.cursor
    total_events = total_evidence = pages = 0
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=args.output.name + ".", suffix=".tmp", dir=args.output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        append(temporary, {"record_type": "bundle-header", "schema": 1, "scope": scope_value,
            "since": args.since, "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "server": args.server, "host_header": args.host_header, "token_env": args.token_env,
            "parent_cursor": args.cursor})
        follow_deadline = None
        while True:
            page_query = dict(query)
            if cursor:
                page_query["cursor"] = cursor
            url = args.server.rstrip("/") + "/api/streams/evidence?" + urllib.parse.urlencode(page_query, doseq=True)
            page = stream_page(url=url, token=token, host_header=args.host_header,
                               output=temporary, history_limit=args.history_limit,
                               follow_deadline=follow_deadline)
            pages += 1
            total_events += page["events"]
            total_evidence += page["evidence"]
            if page["snapshot"] != 1:
                raise RuntimeError("Cortex stream did not emit exactly one snapshot")
            if page["cursor"]:
                cursor = page["cursor"]
            if page["truncated"]:
                if not cursor:
                    raise RuntimeError("truncated Cortex history did not provide a resume cursor")
                continue
            if not page["caught_up"]:
                raise RuntimeError("Cortex stream ended before historical catch-up")
            if follow_deadline is None and args.follow_seconds:
                follow_deadline = time.monotonic() + args.follow_seconds
                continue
            break
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        append(temporary, {"record_type": "bundle-footer",
            "ended_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resume_cursor": cursor, "pages": pages, "events": total_events,
            "evidence_events": total_evidence, "pre_footer_sha256": digest})
        os.replace(temporary, args.output)
    except Exception as error:
        temporary.unlink(missing_ok=True)
        parser.exit(1, f"capture failed: {error}\n")
    print(json.dumps({"output": str(args.output.resolve()), "resume_cursor": cursor,
                      "pages": pages, "events": total_events, "evidence_events": total_evidence,
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
