#!/usr/bin/env python3
"""Build a safe, non-duplicated JSONL corpus from a Codex transcript.

The session deep-dive redaction contract deliberately rejects source strings
that contain ``[REDACTED`` followed by any other content. This helper creates a
derived JSONL corpus by withholding each such string in full. It reports only
counts and cryptographic digests; it never prints source content.

Codex also emits ``event_msg`` UI projections for canonical response items.
The ``item_completed`` projections duplicate messages, command executions, and
tool results already retained as ``response_item`` records, while
``token_count`` is accounting metadata rather than session evidence. Those two
event types are omitted from the derived semantic-review corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path


WITHHELD_VALUE = "[REDACTED]"
WITHHELD_KEY_PREFIX = "SOURCE_REDACTION_MARKER_KEY"
MAX_CONTAINER_NODES = 8_000


def sha256_file(path: Path, byte_limit: int | None = None) -> str:
    digest = hashlib.sha256()
    remaining = byte_limit
    with path.open("rb") as handle:
        while remaining is None or remaining > 0:
            block = handle.read(
                1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
            )
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    if remaining not in {None, 0}:
        raise ValueError(f"source ended {remaining} bytes before requested cutoff")
    return digest.hexdigest()


def sanitize(value, counts):
    sanitized, _nodes = sanitize_with_count(value, counts)
    return sanitized


def sanitize_with_count(value, counts):
    if isinstance(value, str):
        if "[REDACTED" in value:
            counts["withheld_strings"] += 1
            return WITHHELD_VALUE, 1
        stripped = value.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                decoded = json.loads(value)
            except (json.JSONDecodeError, RecursionError):
                decoded = None
            if isinstance(decoded, (dict, list)) and structure_exceeds_budget(decoded):
                counts["withheld_encoded_structures"] += 1
                return WITHHELD_VALUE, 1
        return value, 1
    if isinstance(value, list):
        result = []
        nodes = 1
        for item in value:
            safe_item, child_nodes = sanitize_with_count(item, counts)
            nodes += child_nodes
            if nodes > MAX_CONTAINER_NODES:
                counts["withheld_structures"] += 1
                return WITHHELD_VALUE, 1
            result.append(safe_item)
        return result, nodes
    if isinstance(value, dict):
        result = {}
        nodes = 1
        for key, item in value.items():
            safe_key = key
            if isinstance(key, str) and "[REDACTED" in key:
                counts["withheld_keys"] += 1
                safe_key = f"{WITHHELD_KEY_PREFIX}_{counts['withheld_keys']}"
            while safe_key in result:
                counts["key_collisions"] += 1
                safe_key = f"{safe_key}_{counts['key_collisions']}"
            safe_item, child_nodes = sanitize_with_count(item, counts)
            nodes += child_nodes
            if nodes > MAX_CONTAINER_NODES:
                counts["withheld_structures"] += 1
                return WITHHELD_VALUE, 1
            result[safe_key] = safe_item
        return result, nodes
    return value, 1


def structure_exceeds_budget(value):
    nodes = 0
    stack = [value]
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > MAX_CONTAINER_NODES:
            return True
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return False


def sanitize_record(record, counts):
    if not isinstance(record, dict):
        return sanitize(record, counts)
    record = dict(record)
    if record.get("type") == "compacted" and isinstance(record.get("payload"), dict):
        payload = dict(record["payload"])
        history = payload.get("replacement_history")
        if isinstance(history, list):
            counts["withheld_compaction_histories"] += 1
            counts["withheld_compaction_items"] += len(history)
            payload["replacement_history"] = []
            record["payload"] = payload
    result = {}
    nodes = 1
    for key, item in record.items():
        safe_key = key
        if isinstance(key, str) and "[REDACTED" in key:
            counts["withheld_keys"] += 1
            safe_key = f"{WITHHELD_KEY_PREFIX}_{counts['withheld_keys']}"
        while safe_key in result:
            counts["key_collisions"] += 1
            safe_key = f"{safe_key}_{counts['key_collisions']}"
        safe_item, child_nodes = sanitize_with_count(item, counts)
        nodes += child_nodes
        result[safe_key] = safe_item
    if nodes > MAX_CONTAINER_NODES:
        counts["withheld_records"] += 1
        return {
            key: value if key in {"timestamp", "type"} else WITHHELD_VALUE
            for key, value in result.items()
        }
    return result


def regular_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError(f"not a regular file: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--source-byte-limit",
        type=int,
        help="read exactly this immutable prefix of a live JSONL source",
    )
    args = parser.parse_args()

    source = regular_file(args.source)
    source_size = source.stat().st_size
    source_byte_limit = args.source_byte_limit or source_size
    if source_byte_limit <= 0 or source_byte_limit > source_size:
        raise ValueError(
            f"source byte limit must be within 1..{source_size}: {source_byte_limit}"
        )
    destination = args.destination.expanduser().resolve()
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    counts = {
        "source_records": 0,
        "records": 0,
        "omitted_item_completed_events": 0,
        "omitted_token_count_events": 0,
        "withheld_strings": 0,
        "withheld_keys": 0,
        "withheld_structures": 0,
        "withheld_encoded_structures": 0,
        "withheld_compaction_histories": 0,
        "withheld_compaction_items": 0,
        "withheld_records": 0,
        "key_collisions": 0,
    }
    output_digest = hashlib.sha256()
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with source.open("rb") as input_handle, os.fdopen(
            descriptor, "wb"
        ) as output_handle:
            consumed = 0
            line_number = 0
            while consumed < source_byte_limit:
                line = input_handle.readline(source_byte_limit - consumed)
                if not line:
                    raise ValueError("source ended before requested cutoff")
                consumed += len(line)
                line_number += 1
                if not line.endswith(b"\n"):
                    raise ValueError(
                        f"source byte cutoff splits JSONL record at line {line_number}"
                    )
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSON at line {line_number}") from error
                counts["source_records"] += 1
                payload = record.get("payload") if isinstance(record, dict) else None
                if (
                    isinstance(record, dict)
                    and record.get("type") == "event_msg"
                    and isinstance(payload, dict)
                ):
                    if payload.get("type") == "item_completed":
                        counts["omitted_item_completed_events"] += 1
                        continue
                    if payload.get("type") == "token_count":
                        counts["omitted_token_count_events"] += 1
                        continue
                encoded = (
                    json.dumps(
                        sanitize_record(record, counts),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
                output_handle.write(encoded)
                output_digest.update(encoded)
                counts["records"] += 1
    except BaseException:
        destination.unlink(missing_ok=True)
        raise

    receipt = {
        "schema_version": 1,
        "source": {
            "bytes": source_byte_limit,
            "live_file_bytes_at_start": source_size,
            "sha256": sha256_file(source, source_byte_limit),
        },
        "derived": {
            "bytes": destination.stat().st_size,
            "sha256": output_digest.hexdigest(),
        },
        **counts,
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
