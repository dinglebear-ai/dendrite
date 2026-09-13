#!/usr/bin/env python3
"""Build and score the fixed Axon session bake-off from prepared-v4 evidence.

The builder never reads a raw Codex JSONL transcript.  It invokes the frozen
``session-deep-dive verify-prepared`` boundary, independently verifies every
prepared-v4 sidecar and seal, resolves the fixed corpus selectors, and emits a
bounded redacted bundle.  The scorer requires exactly three complete runs and
an externally supplied, identity-blinded qualitative review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

TOOL_VERSION = "lmstudio-session-bakeoff-v2"
CORPUS_EXPECTED_SHA256 = (
    "8e5c2f9bfbf1fea16f45dc935102e9c9bd6867e9ce53561b2d4602335a8cd017"
)
EXPECTED_SOURCE_SHA256 = (
    "9755104caa34833d76c509846821e0f0bdb06e9cb5ae53b7b4f4c92ec5305a90"
)
EXPECTED_SOURCE_BYTES = 157_155_006
EXPECTED_LOG_SHA256 = (
    "28887f13dd8cd52f9a118561975e6c2d8ea9b83f5b29c55ff96c006c80461e9b"
)
EXPECTED_LOG_BYTES = 13_610
PREPARED_CONTRACT = "session-deep-dive-prepared-v4"
REDACTION_CONTRACT = "session-deep-dive-redaction-v6"
VALIDATION_CONTRACT = "session-deep-dive-prepared-validation-v1"
MEDIA_CONTRACT = "session-deep-dive-media-ledger-v1"
PREPARED_FILENAMES = {
    "manifest": "manifest.json",
    "seal": "prepare-seal.json",
    "record_index": "record-index.json",
    "unit_index": "unit-index.json",
    "media_ledger": "media-ledger.json",
}

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_LOG_BYTES = 1024 * 1024
MAX_CONTENT_TEXT_BYTES = 32_768
MAX_RESPONSE_TEXT_BYTES = 4_096
MAX_PACKET_UNITS = 24
MAX_PACKET_CANONICAL_BYTES = 16_384
MAX_CONSERVATIVE_INPUT_TOKENS = 20_480
MAX_OUTPUT_TOKENS = 8_192
MAX_REASONING_TOKENS = 4_096
RESERVED_CONTEXT_TOKENS = 4_096
TARGET_CONTEXT_TOKENS = 32_768
REQUIRED_REPEATS = 3
PACKET_ROTATION_OFFSETS = (0, 3, 6)
MAX_CALLBACK_DEADLINE_MS = 7_200_000
MAX_CLAIMS = 128
MAX_CITATIONS = 32
MAX_REVIEWERS = 10

SYNTHETIC_VISION_SHA256 = (
    "32d8d17e13795dd62f3e8a39d033ccecd74ab4a707b77515f7c8dd0ba6cb25d3"
)
SYNTHETIC_VISION_GOLD = {
    "top_bar_present": True,
    "left_sidebar_present": True,
    "main_panel_present": True,
    "status_text": "ERR",
    "status_state": "error",
    "anomaly_color": "rose",
    "anomaly_position": "upper_right",
    "anomaly_shape": "square",
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
BLIND_CANDIDATE_RE = re.compile(r"^candidate-[0-9a-f]{12}$")
BLIND_REVIEWER_RE = re.compile(r"^reviewer-[0-9a-f]{12}$")
SECRET_RE = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|"
    r"(?:password|secret|api[_ -]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
RAW_URI_RE = re.compile(r"(?:data:|file:|blob:)", re.IGNORECASE)
HOME_OR_TEMP_PATH_RE = re.compile(
    r"(?:^|[\s'\"(])(?:~(?:/|[A-Za-z0-9._-]+/)|"
    r"/(?:Users|home|private|tmp|var/folders|Volumes)/)",
    re.IGNORECASE,
)
WINDOWS_PATH_RE = re.compile(
    r"(?:^|[\s'\"(])(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+|"
    r"[A-Za-z0-9._-]+\\[A-Za-z0-9._-]+)"
)
UNC_PATH_RE = re.compile(r"(?:^|[\s'\"(])\\{2,}[^\\\s]+\\+[^\\\s]+")
PARENT_PATH_RE = re.compile(r"(?:^|[\s'\"(])\.\./")
BASE64_LIKE_RE = re.compile(
    r"(?<![A-Za-z0-9_+/=-])(?:[A-Za-z0-9_+/=-]{128,})(?![A-Za-z0-9_+/=-])"
)
FORBIDDEN_KEY_RE = re.compile(
    r"(?:^|_)(?:raw(?:_media)?|raw_base64|base64(?:url)?|media_payload|pixels?|"
    r"attachment_path|source_path|absolute_path|home_path|temp_path|file_path|"
    r"secret|password|authorization|api_key)(?:$|_)",
    re.IGNORECASE,
)

STATES = {
    "requested",
    "diagnosed",
    "implemented",
    "test_passed",
    "built",
    "installed",
    "live_verified",
    "observed",
    "unresolved",
    "failed_attempt",
    "not_done",
    "partial",
}
POLARITIES = {"affirmed", "negated", "uncertain"}
DISPOSITIONS = {
    "used",
    "duplicate",
    "administrative",
    "non_substantive",
    "superseded",
    "no_additional_value",
}
SEMANTIC_KINDS = {
    "user_message",
    "assistant_message",
    "tool_call",
    "tool_result",
    "state_observation",
    "screenshot_observation",
    "session_metadata",
}
RUBRIC_DIMENSIONS = [
    "completeness",
    "grounding",
    "state_distinction",
    "wrong_turns",
    "contradictions",
    "actionable_detail",
    "schema_adherence",
    "visual_recall",
    "repeat_consistency",
]


class ContractError(ValueError):
    """An input violated a finite, frozen bake-off contract."""


def fail(message: str) -> None:
    raise ContractError(message)


def reject_constant(value: str) -> None:
    fail(f"non-finite JSON value is forbidden: {value}")


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def assert_finite(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        fail(f"{label} contains a non-finite number")
    if isinstance(value, list):
        for item in value:
            assert_finite(item, label)
    elif isinstance(value, dict):
        for item in value.values():
            assert_finite(item, label)


def canonical_bytes(value: Any) -> bytes:
    assert_finite(value, "canonical value")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def read_regular_bytes(path: Path, label: str, *, limit: int) -> bytes:
    try:
        before = path.stat(follow_symlinks=False)
    except FileNotFoundError as error:
        raise ContractError(f"{label} is missing") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        fail(f"{label} must be a regular non-symlink file")
    if before.st_size > limit:
        fail(f"{label} exceeds the byte limit")
    data = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )
    if identity(before) != identity(after):
        fail(f"{label} changed while being read")
    return data


def parse_strict_json(data: bytes, label: str) -> Any:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as error:
        raise ContractError(f"{label} is not UTF-8") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"{label} is not strict JSON: {error.msg}") from error
    assert_finite(value, label)
    return value


def read_json(
    path: Path, label: str, *, limit: int = MAX_JSON_BYTES
) -> tuple[Any, bytes]:
    data = read_regular_bytes(path, label, limit=limit)
    return parse_strict_json(data, label), data


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        fail(f"{label} must be an array")
    return value


def exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    extra = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if extra:
        fail(f"{label} has unsupported fields: {', '.join(extra)}")
    if missing:
        fail(f"{label} omitted required fields: {', '.join(missing)}")


def optional_keys(
    value: dict[str, Any], required: set[str], optional: set[str], label: str
) -> None:
    extra = sorted(set(value) - required - optional)
    missing = sorted(required - set(value))
    if extra:
        fail(f"{label} has unsupported fields: {', '.join(extra)}")
    if missing:
        fail(f"{label} omitted required fields: {', '.join(missing)}")


def require_string(value: Any, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        fail(f"{label} must be a non-empty bounded string")
    return value


def require_id(value: Any, label: str) -> str:
    text = require_string(value, label, 128)
    if not ID_RE.fullmatch(text):
        fail(f"{label} has an invalid identifier")
    return text


def require_sha(value: Any, label: str) -> str:
    text = require_string(value, label, 64)
    if not SHA256_RE.fullmatch(text):
        fail(f"{label} must be a lowercase SHA-256 digest")
    return text


def require_integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        fail(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def require_turn_id(value: Any, label: str) -> str:
    text = require_string(value, label, 64)
    if text != "session-meta" and not UUID_RE.fullmatch(text):
        fail(f"{label} must be an exact turn UUID or session-meta")
    return text


def unsafe_findings(value: Any, label: str = "value") -> list[str]:
    """Defense-in-depth check that preserves safe repo paths and HTTPS URLs."""

    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if FORBIDDEN_KEY_RE.search(key):
                findings.append(f"{label}.{key}: forbidden data-bearing field")
            findings.extend(unsafe_findings(item, f"{label}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(unsafe_findings(item, f"{label}[{index}]"))
    elif isinstance(value, str):
        if RAW_URI_RE.search(value):
            findings.append(f"{label}: raw media or local-file URI")
        if HOME_OR_TEMP_PATH_RE.search(value):
            findings.append(f"{label}: home, absolute private, or temporary path")
        if WINDOWS_PATH_RE.search(value):
            findings.append(f"{label}: Windows or UNC path")
        if UNC_PATH_RE.search(value):
            findings.append(f"{label}: Windows or UNC path")
        if PARENT_PATH_RE.search(value):
            findings.append(f"{label}: parent-relative path")
        if (
            (len(value) != 64 or not SHA256_RE.fullmatch(value))
            and BASE64_LIKE_RE.search(value)
        ):
            findings.append(f"{label}: base64/base64url-like payload")
        if SECRET_RE.search(value):
            findings.append(f"{label}: secret-like payload")
    return findings


def assert_safe(value: Any, label: str) -> None:
    findings = unsafe_findings(value, label)
    if findings:
        fail(f"unsafe {label}: {findings[0]}")


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = require_object(value, "corpus manifest")
    exact_keys(
        manifest,
        {
            "schema_version",
            "kind",
            "corpus_version",
            "session_id",
            "source_contracts",
            "execution_contract",
            "scoring_contract",
            "evaluation_limitations",
            "packets",
            "gold_facts",
            "critical_contradictions",
            "blinded_review_rubric",
            "manifest_sha256",
        },
        "corpus manifest",
    )
    if manifest["schema_version"] != 2 or manifest["kind"] != "fixed_session_bakeoff_corpus":
        fail("unsupported corpus manifest contract")
    require_id(manifest["corpus_version"], "corpus version")
    if not UUID_RE.fullmatch(require_string(manifest["session_id"], "session id", 64)):
        fail("session id must be a UUID")
    declared = require_sha(manifest["manifest_sha256"], "manifest sha256")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256")
    computed = sha256_value(unsigned)
    if declared != CORPUS_EXPECTED_SHA256 or computed != CORPUS_EXPECTED_SHA256:
        fail("corpus differs from the compiled reviewed corpus; resealing is forbidden")

    contracts = require_object(manifest["source_contracts"], "source contracts")
    exact_keys(
        contracts,
        {
            "prepared",
            "redaction",
            "prepared_validation",
            "media_ledger",
            "expected_source_sha256",
            "expected_source_bytes",
            "expected_corroborating_log_sha256",
            "expected_corroborating_log_bytes",
            "authority_policy",
        },
        "source contracts",
    )
    expected_contracts = {
        "prepared": PREPARED_CONTRACT,
        "redaction": REDACTION_CONTRACT,
        "prepared_validation": VALIDATION_CONTRACT,
        "media_ledger": MEDIA_CONTRACT,
        "expected_source_sha256": EXPECTED_SOURCE_SHA256,
        "expected_source_bytes": EXPECTED_SOURCE_BYTES,
        "expected_corroborating_log_sha256": EXPECTED_LOG_SHA256,
        "expected_corroborating_log_bytes": EXPECTED_LOG_BYTES,
    }
    for key, expected in expected_contracts.items():
        if contracts[key] != expected:
            fail(f"source contract {key} changed")
    require_string(contracts["authority_policy"], "authority policy", 2048)

    execution = require_object(manifest["execution_contract"], "execution contract")
    expected_execution = {
        "max_semantic_units_per_packet": MAX_PACKET_UNITS,
        "max_canonical_packet_bytes": MAX_PACKET_CANONICAL_BYTES,
        "max_conservative_input_tokens": MAX_CONSERVATIVE_INPUT_TOKENS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_reasoning_tokens": MAX_REASONING_TOKENS,
        "reserved_context_tokens": RESERVED_CONTEXT_TOKENS,
        "target_context_tokens": TARGET_CONTEXT_TOKENS,
        "required_repeats": REQUIRED_REPEATS,
        "packet_rotation_offsets": list(PACKET_ROTATION_OFFSETS),
    }
    if execution != expected_execution:
        fail("execution contract differs from the frozen 32K envelope")
    if MAX_CONSERVATIVE_INPUT_TOKENS + MAX_OUTPUT_TOKENS + RESERVED_CONTEXT_TOKENS != TARGET_CONTEXT_TOKENS:
        fail("internal context envelope is inconsistent")

    scoring = require_object(manifest["scoring_contract"], "scoring contract")
    if scoring != {
        "median_hard_weight": 0.5,
        "worst_hard_weight": 0.2,
        "median_blinded_qualitative_weight": 0.2,
        "repeat_consistency_weight": 0.1,
        "qualitative_dimensions": 9,
        "qualitative_points_per_dimension": 5,
    }:
        fail("scoring contract changed")

    limitations = require_list(manifest["evaluation_limitations"], "limitations")
    if len(limitations) != 4:
        fail("the four frozen evaluation limitations are required")
    for item in limitations:
        require_string(item, "evaluation limitation", 768)

    packets = require_list(manifest["packets"], "packets")
    expected_ids = ["A", "B1", "B2", "C", "D", "E1", "E2", "F"]
    if [row.get("packet_id") if isinstance(row, dict) else None for row in packets] != expected_ids:
        fail("fixed packet identity or order changed")
    support_by_packet: dict[str, set[int | str]] = {}
    visual_groups: set[str] = set()
    multi_groups: set[str] = set()
    for packet in packets:
        exact_keys(
            require_object(packet, "packet"),
            {"packet_id", "title", "primary_units", "corroborating_units"},
            "packet",
        )
        packet_id = require_id(packet["packet_id"], "packet id")
        require_string(packet["title"], f"packet {packet_id} title", 256)
        primary = require_list(packet["primary_units"], f"packet {packet_id} primary")
        logs = require_list(packet["corroborating_units"], f"packet {packet_id} logs")
        if not primary or len(primary) + len(logs) > MAX_PACKET_UNITS:
            fail(f"packet {packet_id} has an invalid raw selector count")
        selectors: set[tuple[int, str]] = set()
        support: set[int | str] = set()
        for selector in primary:
            selector = require_object(selector, "primary selector")
            optional_keys(
                selector,
                {"record_id", "turn_id"},
                {"visual_group", "multi_image"},
                "primary selector",
            )
            record_id = require_integer(selector["record_id"], "record id", 1, 10_000_000)
            turn_id = require_turn_id(selector["turn_id"], "turn id")
            if (record_id, turn_id) in selectors:
                fail(f"packet {packet_id} repeats a selector")
            selectors.add((record_id, turn_id))
            support.add(record_id)
            if "visual_group" in selector:
                group = require_id(selector["visual_group"], "visual group")
                visual_groups.add(group)
                if selector.get("multi_image") is True:
                    multi_groups.add(group)
                elif "multi_image" in selector:
                    fail("multi_image must be true when present")
            elif "multi_image" in selector:
                fail("multi_image requires a visual group")
        seen_logs: set[str] = set()
        for selector in logs:
            exact_keys(
                require_object(selector, "corroborating selector"),
                {"log_id", "line_start", "line_end"},
                "corroborating selector",
            )
            log_id = require_id(selector["log_id"], "log id")
            start = require_integer(selector["line_start"], "line start", 1, 1_000_000)
            require_integer(selector["line_end"], "line end", start, 1_000_000)
            if log_id in seen_logs:
                fail(f"packet {packet_id} repeats a log id")
            seen_logs.add(log_id)
            support.add(log_id)
        support_by_packet[packet_id] = support
    if len(visual_groups) < 3 or not multi_groups:
        fail("corpus lacks the frozen visual stratification")

    facts = require_list(manifest["gold_facts"], "gold facts")
    if [row.get("fact_id") if isinstance(row, dict) else None for row in facts] != [
        f"G{number:02d}" for number in range(1, 43)
    ]:
        fail("gold facts must be exact G01-G42 in order")
    for index, fact in enumerate(facts, 1):
        fact = require_object(fact, "gold fact")
        exact_keys(
            fact,
            {
                "fact_id",
                "packet_id",
                "weight",
                "critical",
                "allowed_states",
                "support_groups",
                "example_text",
            },
            f"gold fact G{index:02d}",
        )
        fact_id = require_id(fact["fact_id"], "fact id")
        packet_id = require_id(fact["packet_id"], f"{fact_id} packet")
        expected_critical = index <= 12
        if fact["critical"] is not expected_critical or fact["weight"] != (2 if expected_critical else 1):
            fail(f"{fact_id} criticality or weight changed")
        states = require_list(fact["allowed_states"], f"{fact_id} states")
        if not states or len(states) != len(set(states)) or any(state not in STATES for state in states):
            fail(f"{fact_id} states are invalid")
        groups = require_list(fact["support_groups"], f"{fact_id} support groups")
        if not groups:
            fail(f"{fact_id} has no support groups")
        for group in groups:
            group = require_list(group, f"{fact_id} support group")
            if not group or not any(item in support_by_packet.get(packet_id, set()) for item in group):
                fail(f"{fact_id} support group has no local selector")
            for item in group:
                if isinstance(item, bool) or not isinstance(item, (int, str)):
                    fail(f"{fact_id} support selector has an invalid type")
        require_string(fact["example_text"], f"{fact_id} example", 2048)
    if sum(int(fact["weight"]) for fact in facts) != 54:
        fail("gold fact weight denominator changed")
    g02 = facts[1]
    if g02["support_groups"] != [[3772], [3778, 3783, 3791], [4986]]:
        fail("G02 support changed; record 3900 is not Enter verification evidence")

    contradictions = require_list(manifest["critical_contradictions"], "contradictions")
    if [row.get("rule_id") if isinstance(row, dict) else None for row in contradictions] != [
        "C01", "C02", "C07", "C09", "C10", "C12"
    ]:
        fail("critical contradiction rule set changed")
    for rule in contradictions:
        exact_keys(
            require_object(rule, "contradiction rule"),
            {"rule_id", "predicate_label", "forbidden_polarities", "safe_polarities"},
            "contradiction rule",
        )
        require_id(rule["predicate_label"], "contradiction predicate label")
        if rule["forbidden_polarities"] != ["affirmed"] or rule["safe_polarities"] != ["negated", "uncertain"]:
            fail("contradiction polarity contract changed")

    rubric = require_list(manifest["blinded_review_rubric"], "rubric")
    if [row.get("dimension") if isinstance(row, dict) else None for row in rubric] != RUBRIC_DIMENSIONS:
        fail("blinded rubric dimensions changed")
    for row in rubric:
        exact_keys(require_object(row, "rubric row"), {"dimension", "max_points", "question"}, "rubric row")
        if row["max_points"] != 5:
            fail("rubric points changed")
        require_string(row["question"], "rubric question", 512)
    return manifest


def load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    value, raw = read_json(path, "corpus manifest", limit=2 * 1024 * 1024)
    return validate_manifest(value), raw


def validate_source_selector(value: Any, label: str) -> dict[str, Any]:
    selector = require_object(value, label)
    exact_keys(selector, {"record_id", "turn_id"}, label)
    require_integer(selector["record_id"], f"{label} record id", 1, 10_000_000)
    require_turn_id(selector["turn_id"], f"{label} turn id")
    return selector


def validate_prepared_manifest(value: Any, raw_hashes: dict[str, str]) -> dict[str, Any]:
    prepared = require_object(value, "prepared manifest")
    exact_keys(
        prepared,
        {
            "schema_version",
            "prepared_contract",
            "redaction_contract",
            "session_id",
            "source",
            "record_index_sha256",
            "unit_index_sha256",
            "media_ledger_sha256",
        },
        "prepared manifest",
    )
    if prepared["schema_version"] != 4 or prepared["prepared_contract"] != PREPARED_CONTRACT or prepared["redaction_contract"] != REDACTION_CONTRACT:
        fail("prepared manifest is not the exact prepared-v4/redaction-v6 contract")
    if not UUID_RE.fullmatch(require_string(prepared["session_id"], "prepared session id", 64)):
        fail("prepared session id is invalid")
    source = require_object(prepared["source"], "prepared source")
    exact_keys(source, {"sha256", "bytes"}, "prepared source")
    if require_sha(source["sha256"], "prepared source sha256") != EXPECTED_SOURCE_SHA256 or require_integer(source["bytes"], "prepared source bytes", 1, 1_000_000_000) != EXPECTED_SOURCE_BYTES:
        fail("prepared source differs from the pinned target transcript")
    for field, sidecar in (
        ("record_index_sha256", "record_index"),
        ("unit_index_sha256", "unit_index"),
        ("media_ledger_sha256", "media_ledger"),
    ):
        if require_sha(prepared[field], f"prepared {field}") != raw_hashes[sidecar]:
            fail(f"prepared manifest does not bind {sidecar}")
    return prepared


def validate_record_index(value: Any) -> dict[str, Any]:
    index = require_object(value, "record index")
    exact_keys(index, {"schema_version", "kind", "source_sha256", "records"}, "record index")
    if index["schema_version"] != 4 or index["kind"] != "session-deep-dive-record-index-v4" or index["source_sha256"] != EXPECTED_SOURCE_SHA256:
        fail("record index contract or source binding is invalid")
    records = require_list(index["records"], "record index records")
    if not records or len(records) > 100_000:
        fail("record index count is invalid")
    seen: set[tuple[int, str]] = set()
    for row in records:
        exact_keys(require_object(row, "record index row"), {"record_id", "turn_id", "normalized_unit_ids"}, "record index row")
        record_id = require_integer(row["record_id"], "record index id", 1, 10_000_000)
        turn_id = require_turn_id(row["turn_id"], "record index turn")
        if (record_id, turn_id) in seen:
            fail("record index selector is ambiguous")
        seen.add((record_id, turn_id))
        unit_ids = require_list(row["normalized_unit_ids"], "record normalized units")
        if not unit_ids or len(unit_ids) > 32 or len(unit_ids) != len(set(unit_ids)):
            fail("record normalized-unit mapping is empty or ambiguous")
        for unit_id in unit_ids:
            require_id(unit_id, "normalized unit id")
    assert_safe(index, "record index")
    return index


def validate_unit_index(value: Any) -> dict[str, Any]:
    index = require_object(value, "unit index")
    exact_keys(index, {"schema_version", "kind", "source_sha256", "units"}, "unit index")
    if index["schema_version"] != 4 or index["kind"] != "session-deep-dive-unit-index-v4" or index["source_sha256"] != EXPECTED_SOURCE_SHA256:
        fail("unit index contract or source binding is invalid")
    units = require_list(index["units"], "normalized units")
    if not units or len(units) > 100_000:
        fail("unit index count is invalid")
    seen: set[str] = set()
    for unit in units:
        exact_keys(
            require_object(unit, "normalized unit"),
            {"normalized_unit_id", "source_selectors", "semantic_kind", "text", "content_sha256"},
            "normalized unit",
        )
        unit_id = require_id(unit["normalized_unit_id"], "normalized unit id")
        if unit_id in seen:
            fail("normalized unit id is ambiguous")
        seen.add(unit_id)
        selectors = require_list(unit["source_selectors"], "normalized unit source selectors")
        if not selectors or len(selectors) > 64:
            fail("normalized unit source selector count is invalid")
        keys: set[tuple[int, str]] = set()
        for selector in selectors:
            checked = validate_source_selector(selector, "unit source selector")
            key = (checked["record_id"], checked["turn_id"])
            if key in keys:
                fail("normalized unit repeats a source selector")
            keys.add(key)
        if unit["semantic_kind"] not in SEMANTIC_KINDS:
            fail("normalized unit semantic kind is unsupported")
        require_string(unit["text"], "normalized unit text", MAX_CONTENT_TEXT_BYTES)
        content = {"semantic_kind": unit["semantic_kind"], "text": unit["text"]}
        if require_sha(unit["content_sha256"], "normalized unit content hash") != sha256_value(content):
            fail("normalized unit content hash does not match")
    assert_safe(index, "unit index")
    return index


def validate_media_ledger(value: Any) -> dict[str, Any]:
    ledger = require_object(value, "media ledger")
    exact_keys(
        ledger,
        {"schema_version", "contract", "source_sha256", "occurrences", "assets", "groups"},
        "media ledger",
    )
    if ledger["schema_version"] != 1 or ledger["contract"] != MEDIA_CONTRACT or ledger["source_sha256"] != EXPECTED_SOURCE_SHA256:
        fail("media ledger contract or source binding is invalid")
    assets = require_list(ledger["assets"], "media assets")
    asset_map: dict[str, dict[str, Any]] = {}
    for asset in assets:
        exact_keys(require_object(asset, "media asset"), {"asset_sha256", "media_type", "width", "height", "byte_length"}, "media asset")
        digest = require_sha(asset["asset_sha256"], "media asset sha256")
        if digest in asset_map:
            fail("media asset digest is duplicated")
        if asset["media_type"] not in {"image/png", "image/jpeg", "image/webp"}:
            fail("media asset type is unsupported")
        require_integer(asset["width"], "media width", 1, 100_000)
        require_integer(asset["height"], "media height", 1, 100_000)
        require_integer(asset["byte_length"], "media bytes", 1, 100_000_000)
        asset_map[digest] = asset
    occurrences = require_list(ledger["occurrences"], "media occurrences")
    occurrence_map: dict[str, dict[str, Any]] = {}
    selector_occurrences: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        exact_keys(
            require_object(occurrence, "media occurrence"),
            {"occurrence_id", "record_id", "turn_id", "ordinal", "asset_sha256", "visual_group"},
            "media occurrence",
        )
        occurrence_id = require_id(occurrence["occurrence_id"], "media occurrence id")
        if occurrence_id in occurrence_map:
            fail("media occurrence id is duplicated")
        record_id = require_integer(occurrence["record_id"], "media record id", 1, 10_000_000)
        turn_id = require_turn_id(occurrence["turn_id"], "media turn id")
        require_integer(occurrence["ordinal"], "media ordinal", 1, 1024)
        digest = require_sha(occurrence["asset_sha256"], "media occurrence asset")
        if digest not in asset_map:
            fail("media occurrence references an unknown asset")
        group = require_id(occurrence["visual_group"], "media visual group")
        occurrence_map[occurrence_id] = occurrence
        selector_occurrences[(record_id, turn_id, group)].append(occurrence)
    groups = require_list(ledger["groups"], "media groups")
    group_map: dict[str, dict[str, Any]] = {}
    for group in groups:
        exact_keys(require_object(group, "media group"), {"visual_group", "occurrence_ids", "asset_sha256s"}, "media group")
        group_id = require_id(group["visual_group"], "media group id")
        if group_id in group_map:
            fail("media group id is duplicated")
        occurrence_ids = require_list(group["occurrence_ids"], "media group occurrences")
        digests = require_list(group["asset_sha256s"], "media group assets")
        if not occurrence_ids or len(occurrence_ids) != len(set(occurrence_ids)) or not digests or len(digests) != len(set(digests)):
            fail("media group membership is empty or duplicated")
        for occurrence_id in occurrence_ids:
            require_id(occurrence_id, "media group occurrence id")
            if occurrence_id not in occurrence_map or occurrence_map[occurrence_id]["visual_group"] != group_id:
                fail("media group occurrence binding is invalid")
        for digest in digests:
            require_sha(digest, "media group asset sha256")
        expected_digests = sorted({occurrence_map[item]["asset_sha256"] for item in occurrence_ids})
        if digests != expected_digests:
            fail("media group assets do not exactly match its occurrences")
        group_map[group_id] = group
    if set(group_map) != {occurrence["visual_group"] for occurrence in occurrences}:
        fail("media group ledger is incomplete")
    assert_safe(ledger, "media ledger")
    ledger["_asset_map"] = asset_map
    ledger["_occurrence_map"] = occurrence_map
    ledger["_selector_occurrences"] = selector_occurrences
    ledger["_group_map"] = group_map
    return ledger


def validate_prepare_seal(value: Any, hashes: dict[str, str]) -> dict[str, Any]:
    seal = require_object(value, "prepare seal")
    exact_keys(
        seal,
        {
            "schema_version",
            "kind",
            "prepared_contract",
            "redaction_contract",
            "source_sha256",
            "manifest_sha256",
            "record_index_sha256",
            "unit_index_sha256",
            "media_ledger_sha256",
        },
        "prepare seal",
    )
    expected = {
        "schema_version": 4,
        "kind": "session-deep-dive-prepare-seal-v4",
        "prepared_contract": PREPARED_CONTRACT,
        "redaction_contract": REDACTION_CONTRACT,
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "manifest_sha256": hashes["manifest"],
        "record_index_sha256": hashes["record_index"],
        "unit_index_sha256": hashes["unit_index"],
        "media_ledger_sha256": hashes["media_ledger"],
    }
    if seal != expected:
        fail("prepare seal does not bind the exact prepared-v4 closure")
    return seal


def validate_validation_receipt(value: Any, hashes: dict[str, str]) -> dict[str, Any]:
    receipt = require_object(value, "fresh validation receipt")
    exact_keys(
        receipt,
        {
            "schema_version",
            "validation_contract",
            "validated",
            "source_sha256",
            "manifest_sha256",
            "prepare_seal_sha256",
            "media_ledger_sha256",
            "unit_index_sha256",
            "record_index_sha256",
            "prepared_contract",
            "redaction_contract",
        },
        "fresh validation receipt",
    )
    expected = {
        "schema_version": 1,
        "validation_contract": VALIDATION_CONTRACT,
        "validated": True,
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "manifest_sha256": hashes["manifest"],
        "prepare_seal_sha256": hashes["seal"],
        "media_ledger_sha256": hashes["media_ledger"],
        "unit_index_sha256": hashes["unit_index"],
        "record_index_sha256": hashes["record_index"],
        "prepared_contract": PREPARED_CONTRACT,
        "redaction_contract": REDACTION_CONTRACT,
    }
    if receipt != expected:
        fail("fresh validation receipt does not bind the exact prepared closure")
    return receipt


def invoke_prepared_validator(validator: Path, workdir: Path) -> dict[str, Any]:
    validator_data = read_regular_bytes(validator, "prepared validator", limit=4 * 1024 * 1024)
    del validator_data
    command = [sys.executable, str(validator), "verify-prepared", "--work-dir", str(workdir)]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=30,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except subprocess.TimeoutExpired as error:
        raise ContractError("prepared validator exceeded 30 seconds") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace")[:512].strip()
        fail(f"prepared validator failed closed: {detail or 'no diagnostic'}")
    if len(completed.stdout) > 64 * 1024:
        fail("prepared validator receipt exceeds the byte limit")
    return require_object(parse_strict_json(completed.stdout, "fresh validation receipt"), "fresh validation receipt")


def load_prepared_v4(workdir: Path, validator: Path) -> dict[str, Any]:
    try:
        directory = workdir.stat(follow_symlinks=False)
    except FileNotFoundError as error:
        raise ContractError("prepared workdir is missing") from error
    if stat.S_ISLNK(directory.st_mode) or not stat.S_ISDIR(directory.st_mode):
        fail("prepared workdir must be a non-symlink directory")
    if any(entry.name.lower().endswith((".jsonl", ".jsonl.gz")) for entry in workdir.iterdir()):
        fail("prepared workdir contains raw JSONL")
    values: dict[str, Any] = {}
    raws: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    for key, filename in PREPARED_FILENAMES.items():
        values[key], raws[key] = read_json(workdir / filename, f"prepared {key}")
        hashes[key] = sha256_bytes(raws[key])
    prepared = validate_prepared_manifest(values["manifest"], hashes)
    record_index = validate_record_index(values["record_index"])
    unit_index = validate_unit_index(values["unit_index"])
    media_ledger = validate_media_ledger(values["media_ledger"])
    validate_prepare_seal(values["seal"], hashes)
    fresh = validate_validation_receipt(invoke_prepared_validator(validator, workdir), hashes)
    if prepared["session_id"] == "":
        fail("prepared session id is missing")

    record_map: dict[tuple[int, str], list[str]] = {
        (row["record_id"], row["turn_id"]): row["normalized_unit_ids"]
        for row in record_index["records"]
    }
    unit_map = {row["normalized_unit_id"]: row for row in unit_index["units"]}
    for selector, unit_ids in record_map.items():
        for unit_id in unit_ids:
            if unit_id not in unit_map:
                fail("record index references an unknown normalized unit")
            reciprocal = {
                (row["record_id"], row["turn_id"])
                for row in unit_map[unit_id]["source_selectors"]
            }
            if selector not in reciprocal:
                fail("record/unit index mapping is not reciprocal")
    for unit_id, unit in unit_map.items():
        for selector in unit["source_selectors"]:
            key = (selector["record_id"], selector["turn_id"])
            if unit_id not in record_map.get(key, []):
                fail("unit/record index mapping is not reciprocal")
    return {
        "manifest": prepared,
        "record_index": record_index,
        "unit_index": unit_index,
        "media_ledger": media_ledger,
        "hashes": hashes,
        "receipt": fresh,
        "receipt_sha256": sha256_value(fresh),
        "record_map": record_map,
        "unit_map": unit_map,
    }


def load_corroborating_log(path: Path) -> tuple[list[str], bytes]:
    raw = read_regular_bytes(path, "corroborating partial log", limit=MAX_LOG_BYTES)
    if len(raw) != EXPECTED_LOG_BYTES or sha256_bytes(raw) != EXPECTED_LOG_SHA256:
        fail("corroborating partial log differs from the pinned source")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("corroborating partial log is not UTF-8") from error
    lines = text.splitlines()
    if len(lines) < 178:
        fail("corroborating partial log has too few lines")
    return lines, raw


def selection_visual_receipt(
    selector: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any] | None:
    group = selector.get("visual_group")
    if group is None:
        return None
    occurrences = ledger["_selector_occurrences"].get(
        (selector["record_id"], selector["turn_id"], group), []
    )
    if not occurrences:
        fail(f"visual selector {group} has no bound occurrence")
    group_row = ledger["_group_map"].get(group)
    if group_row is None:
        fail(f"visual selector {group} has no bound group")
    asset_hashes = group_row["asset_sha256s"]
    if selector.get("multi_image") is True and len(set(asset_hashes)) < 2:
        fail(f"multi-image group {group} has fewer than two distinct bound assets")
    return {
        "visual_group": group,
        "occurrence_ids": sorted(row["occurrence_id"] for row in occurrences),
        "asset_sha256s": asset_hashes,
        "multi_image": selector.get("multi_image", False),
    }


def build_bundle_value(
    manifest: dict[str, Any],
    corpus_raw: bytes,
    prepared: dict[str, Any],
    log_lines: list[str],
    log_raw: bytes,
) -> dict[str, Any]:
    if prepared["manifest"]["session_id"] != manifest["session_id"]:
        fail("prepared session does not match the fixed corpus")
    packets: list[dict[str, Any]] = []
    selected_hash_rows: list[dict[str, Any]] = []
    for packet in manifest["packets"]:
        packet_id = packet["packet_id"]
        inputs_by_unit: dict[str, dict[str, Any]] = {}
        selection_receipts: list[dict[str, Any]] = []
        for selector in packet["primary_units"]:
            key = (selector["record_id"], selector["turn_id"])
            unit_ids = prepared["record_map"].get(key)
            if not unit_ids:
                fail(f"packet {packet_id} exact record/turn selector is missing")
            visual = selection_visual_receipt(selector, prepared["media_ledger"])
            selection_receipt = {
                "record_id": selector["record_id"],
                "turn_id": selector["turn_id"],
                "normalized_unit_ids": unit_ids,
            }
            if visual is not None:
                selection_receipt["visual_evidence"] = visual
            selection_receipts.append(selection_receipt)
            for unit_id in unit_ids:
                unit = prepared["unit_map"][unit_id]
                output = inputs_by_unit.setdefault(
                    unit_id,
                    {
                        "input_id": f"{packet_id}:unit:{unit_id}",
                        "normalized_unit_id": unit_id,
                        "source_class": "primary_transcript",
                        "source_selectors": unit["source_selectors"],
                        "semantic_kind": unit["semantic_kind"],
                        "text": unit["text"],
                        "content_sha256": unit["content_sha256"],
                        "visual_evidence": [],
                    },
                )
                if visual is not None and visual not in output["visual_evidence"]:
                    output["visual_evidence"].append(visual)
        input_units = list(inputs_by_unit.values())
        for selector in packet["corroborating_units"]:
            start, end = selector["line_start"], selector["line_end"]
            if end > len(log_lines):
                fail(f"packet {packet_id} corroborating log range is out of bounds")
            text = "\n".join(log_lines[start - 1 : end])
            require_string(text, f"packet {packet_id} corroborating log text", MAX_CONTENT_TEXT_BYTES)
            log_input = {
                "input_id": f"{packet_id}:log:{selector['log_id']}",
                "log_id": selector["log_id"],
                "line_start": start,
                "line_end": end,
                "source_class": "corroborating_session_log",
                "authority": "corroborating_not_authoritative",
                "semantic_kind": "corroborating_summary",
                "text": text,
                "content_sha256": sha256_value({"semantic_kind": "corroborating_summary", "text": text}),
                "visual_evidence": [],
            }
            input_units.append(log_input)
            selection_receipts.append(
                {"log_id": selector["log_id"], "line_start": start, "line_end": end}
            )
        if len(input_units) > MAX_PACKET_UNITS:
            fail(f"packet {packet_id} exceeds 24 unique normalized semantic units")
        for unit in input_units:
            selected_hash_rows.append(
                {"input_id": unit["input_id"], "content_sha256": unit["content_sha256"]}
            )
        payload = {"packet_id": packet_id, "title": packet["title"], "input_units": input_units}
        packet_bytes = canonical_bytes(payload)
        if len(packet_bytes) > MAX_PACKET_CANONICAL_BYTES:
            fail(f"packet {packet_id} exceeds the 16,384-byte canonical packet bound")
        packets.append(
            {
                **payload,
                "selection_receipts": selection_receipts,
                "canonical_packet_bytes": len(packet_bytes),
                "canonical_packet_characters": len(packet_bytes.decode("utf-8")),
            }
        )
    binding = {
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "source_bytes": EXPECTED_SOURCE_BYTES,
        "manifest_sha256": prepared["hashes"]["manifest"],
        "prepare_seal_sha256": prepared["hashes"]["seal"],
        "record_index_sha256": prepared["hashes"]["record_index"],
        "unit_index_sha256": prepared["hashes"]["unit_index"],
        "media_ledger_sha256": prepared["hashes"]["media_ledger"],
        "validation_receipt_sha256": prepared["receipt_sha256"],
        "corroborating_log_sha256": sha256_bytes(log_raw),
        "corroborating_log_bytes": len(log_raw),
        "selected_inputs_sha256": sha256_value(selected_hash_rows),
        "corpus_file_sha256": sha256_bytes(corpus_raw),
    }
    bundle: dict[str, Any] = {
        "schema_version": 2,
        "kind": "session_bakeoff_bundle",
        "tool_version": TOOL_VERSION,
        "corpus_sha256": manifest["manifest_sha256"],
        "corpus_manifest": manifest,
        "prepared_binding": binding,
        "execution_contract": manifest["execution_contract"],
        "evaluation_limitations": manifest["evaluation_limitations"],
        "packets": packets,
    }
    assert_safe(bundle, "bundle")
    bundle["bundle_sha256"] = sha256_value(bundle)
    return bundle


def build_bundle(
    corpus_path: Path,
    prepared_workdir: Path,
    corroborating_log: Path,
    validator: Path,
) -> dict[str, Any]:
    manifest, corpus_raw = load_manifest(corpus_path)
    prepared = load_prepared_v4(prepared_workdir, validator)
    log_lines, log_raw = load_corroborating_log(corroborating_log)
    return build_bundle_value(manifest, corpus_raw, prepared, log_lines, log_raw)


def validate_bundle(value: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    bundle = require_object(value, "bundle")
    exact_keys(
        bundle,
        {
            "schema_version",
            "kind",
            "tool_version",
            "corpus_sha256",
            "corpus_manifest",
            "prepared_binding",
            "execution_contract",
            "evaluation_limitations",
            "packets",
            "bundle_sha256",
        },
        "bundle",
    )
    if bundle["schema_version"] != 2 or bundle["kind"] != "session_bakeoff_bundle" or bundle["tool_version"] != TOOL_VERSION:
        fail("unsupported bundle contract")
    if bundle["corpus_sha256"] != CORPUS_EXPECTED_SHA256 or bundle["corpus_manifest"] != manifest:
        fail("bundle does not contain the exact compiled corpus")
    if bundle["execution_contract"] != manifest["execution_contract"] or bundle["evaluation_limitations"] != manifest["evaluation_limitations"]:
        fail("bundle policy changed")
    declared = require_sha(bundle["bundle_sha256"], "bundle sha256")
    unsigned = dict(bundle)
    unsigned.pop("bundle_sha256")
    if sha256_value(unsigned) != declared:
        fail("bundle seal does not match")
    binding = require_object(bundle["prepared_binding"], "prepared binding")
    exact_keys(
        binding,
        {
            "source_sha256",
            "source_bytes",
            "manifest_sha256",
            "prepare_seal_sha256",
            "record_index_sha256",
            "unit_index_sha256",
            "media_ledger_sha256",
            "validation_receipt_sha256",
            "corroborating_log_sha256",
            "corroborating_log_bytes",
            "selected_inputs_sha256",
            "corpus_file_sha256",
        },
        "prepared binding",
    )
    if binding["source_sha256"] != EXPECTED_SOURCE_SHA256 or binding["source_bytes"] != EXPECTED_SOURCE_BYTES or binding["corroborating_log_sha256"] != EXPECTED_LOG_SHA256 or binding["corroborating_log_bytes"] != EXPECTED_LOG_BYTES:
        fail("bundle source binding changed")
    for key, digest in binding.items():
        if key.endswith("sha256"):
            require_sha(digest, f"bundle binding {key}")
    packets = require_list(bundle["packets"], "bundle packets")
    if len(packets) != 8:
        fail("bundle packet count changed")
    seen_inputs: set[str] = set()
    selected_rows: list[dict[str, Any]] = []
    for expected, packet in zip(manifest["packets"], packets, strict=True):
        packet = require_object(packet, "bundle packet")
        exact_keys(
            packet,
            {"packet_id", "title", "input_units", "selection_receipts", "canonical_packet_bytes", "canonical_packet_characters"},
            "bundle packet",
        )
        if packet["packet_id"] != expected["packet_id"] or packet["title"] != expected["title"]:
            fail("bundle packet identity changed")
        units = require_list(packet["input_units"], "bundle input units")
        if not units or len(units) > MAX_PACKET_UNITS:
            fail("bundle unique semantic-unit count is invalid")
        payload = {"packet_id": packet["packet_id"], "title": packet["title"], "input_units": units}
        raw = canonical_bytes(payload)
        if len(raw) > MAX_PACKET_CANONICAL_BYTES or packet["canonical_packet_bytes"] != len(raw) or packet["canonical_packet_characters"] != len(raw.decode("utf-8")):
            fail("bundle packet size attestation changed")
        for unit in units:
            unit = require_object(unit, "bundle input unit")
            input_id = require_id(unit.get("input_id"), "bundle input id")
            if input_id in seen_inputs:
                fail("bundle input id is ambiguous")
            seen_inputs.add(input_id)
            selected_rows.append({"input_id": input_id, "content_sha256": require_sha(unit.get("content_sha256"), "bundle content hash")})
            require_string(unit.get("text"), "bundle input text", MAX_CONTENT_TEXT_BYTES)
            require_list(unit.get("visual_evidence"), "bundle visual evidence")
            if unit.get("source_class") == "primary_transcript":
                exact_keys(
                    unit,
                    {"input_id", "normalized_unit_id", "source_class", "source_selectors", "semantic_kind", "text", "content_sha256", "visual_evidence"},
                    "primary bundle input",
                )
                require_id(unit["normalized_unit_id"], "bundle normalized unit id")
                for selector in require_list(unit["source_selectors"], "bundle source selectors"):
                    validate_source_selector(selector, "bundle source selector")
                if unit["semantic_kind"] not in SEMANTIC_KINDS:
                    fail("bundle semantic kind is unsupported")
                if unit["content_sha256"] != sha256_value({"semantic_kind": unit["semantic_kind"], "text": unit["text"]}):
                    fail("bundle primary content hash changed")
            elif unit.get("source_class") == "corroborating_session_log":
                exact_keys(
                    unit,
                    {"input_id", "log_id", "line_start", "line_end", "source_class", "authority", "semantic_kind", "text", "content_sha256", "visual_evidence"},
                    "corroborating bundle input",
                )
                if unit["authority"] != "corroborating_not_authoritative" or unit["semantic_kind"] != "corroborating_summary":
                    fail("corroborating authority label changed")
                if unit["content_sha256"] != sha256_value({"semantic_kind": unit["semantic_kind"], "text": unit["text"]}):
                    fail("bundle corroborating content hash changed")
            else:
                fail("bundle input source class is unsupported")
        require_list(packet["selection_receipts"], "bundle selection receipts")
    if binding["selected_inputs_sha256"] != sha256_value(selected_rows):
        fail("bundle selected-input closure changed")
    assert_safe(bundle, "bundle")
    return bundle


def write_json(path: Path, value: Any) -> None:
    parent = path.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        fail("output parent must be an existing non-symlink directory")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        fail("output target must be a regular non-symlink file")
    data = canonical_bytes(value) + b"\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_response(value: Any, bundle: dict[str, Any]) -> dict[str, Any]:
    response = require_object(value, "response")
    exact_keys(
        response,
        {"schema_version", "kind", "corpus_sha256", "bundle_sha256", "packet_results", "report_outline"},
        "response",
    )
    if response["schema_version"] != 2 or response["kind"] != "session_bakeoff_response":
        fail("unsupported response contract")
    if response["corpus_sha256"] != bundle["corpus_sha256"] or response["bundle_sha256"] != bundle["bundle_sha256"]:
        fail("response binding does not match the bundle")
    manifest = bundle["corpus_manifest"]
    allowed_predicates = {fact["fact_id"] for fact in manifest["gold_facts"]} | {
        rule["rule_id"] for rule in manifest["critical_contradictions"]
    }
    expected_packets = {packet["packet_id"]: packet for packet in bundle["packets"]}
    results = require_list(response["packet_results"], "packet results")
    if len(results) != len(expected_packets):
        fail("response must contain every packet exactly once")
    seen_packets: set[str] = set()
    claim_ids: set[str] = set()
    for result in results:
        exact_keys(require_object(result, "packet result"), {"packet_id", "claims", "unit_dispositions"}, "packet result")
        packet_id = require_id(result["packet_id"], "response packet id")
        if packet_id not in expected_packets or packet_id in seen_packets:
            fail("response packet is unknown or duplicated")
        seen_packets.add(packet_id)
        allowed_inputs = {unit["input_id"] for unit in expected_packets[packet_id]["input_units"]}
        claims = require_list(result["claims"], f"packet {packet_id} claims")
        if len(claims) > MAX_CLAIMS:
            fail("packet has too many claims")
        for claim in claims:
            exact_keys(
                require_object(claim, "claim"),
                {"claim_id", "predicate_id", "polarity", "state", "text", "citations"},
                "claim",
            )
            claim_id = require_id(claim["claim_id"], "claim id")
            if claim_id in claim_ids:
                fail("claim id is duplicated")
            claim_ids.add(claim_id)
            if claim["predicate_id"] not in allowed_predicates:
                fail("claim predicate is outside the finite reviewed vocabulary")
            if claim["polarity"] not in POLARITIES:
                fail("claim polarity is invalid")
            if claim["state"] not in STATES:
                fail("claim state is invalid")
            require_string(claim["text"], "claim text", MAX_RESPONSE_TEXT_BYTES)
            citations = require_list(claim["citations"], "claim citations")
            if not 1 <= len(citations) <= MAX_CITATIONS or len(citations) != len(set(citations)) or any(citation not in allowed_inputs for citation in citations):
                fail("claim citations are empty, duplicated, excessive, or unresolved")
        dispositions = require_list(result["unit_dispositions"], "unit dispositions")
        observed: list[str] = []
        for disposition in dispositions:
            exact_keys(require_object(disposition, "unit disposition"), {"input_id", "disposition"}, "unit disposition")
            input_id = require_id(disposition["input_id"], "disposition input id")
            if disposition["disposition"] not in DISPOSITIONS:
                fail("unit disposition is invalid")
            observed.append(input_id)
        if len(observed) != len(set(observed)) or set(observed) != allowed_inputs:
            fail(f"packet {packet_id} requires exactly one disposition per input")
    outline = require_list(response["report_outline"], "report outline")
    if not 1 <= len(outline) <= 24:
        fail("report outline must contain 1-24 sections")
    section_ids: set[str] = set()
    for section in outline:
        exact_keys(require_object(section, "outline section"), {"section_id", "title", "purpose", "claim_ids"}, "outline section")
        section_id = require_id(section["section_id"], "outline section id")
        if section_id in section_ids:
            fail("outline section id is duplicated")
        section_ids.add(section_id)
        require_string(section["title"], "outline title", 256)
        require_string(section["purpose"], "outline purpose", 1024)
        refs = require_list(section["claim_ids"], "outline claim ids")
        if len(refs) != len(set(refs)) or any(ref not in claim_ids for ref in refs):
            fail("outline claim reference does not resolve")
    assert_safe(response, "response")
    return response


def citation_supports(
    citation_ids: list[str],
    support_groups: list[list[int | str]],
    input_lookup: dict[str, dict[str, Any]],
) -> bool:
    cited_records: set[int] = set()
    cited_logs: set[str] = set()
    for citation in citation_ids:
        unit = input_lookup[citation]
        if unit["source_class"] == "primary_transcript":
            cited_records.update(row["record_id"] for row in unit["source_selectors"])
        else:
            cited_logs.add(unit["log_id"])
    return all(
        any(
            (isinstance(item, int) and item in cited_records)
            or (isinstance(item, str) and item in cited_logs)
            for item in group
        )
        for group in support_groups
    )


def score_response(
    response: dict[str, Any], manifest: dict[str, Any], bundle: dict[str, Any], run_index: int
) -> dict[str, Any]:
    input_lookup = {
        unit["input_id"]: unit for packet in bundle["packets"] for unit in packet["input_units"]
    }
    claims: list[dict[str, Any]] = []
    for result in response["packet_results"]:
        claims.extend({**claim, "packet_id": result["packet_id"]} for claim in result["claims"])
    facts_by_id = {fact["fact_id"]: fact for fact in manifest["gold_facts"]}
    matched_claims: dict[str, str] = {}
    matched_states: dict[str, str] = {}
    for fact in manifest["gold_facts"]:
        candidates = [
            claim
            for claim in claims
            if claim["packet_id"] == fact["packet_id"]
            and claim["predicate_id"] == fact["fact_id"]
            and claim["polarity"] == "affirmed"
            and claim["state"] in fact["allowed_states"]
            and citation_supports(claim["citations"], fact["support_groups"], input_lookup)
        ]
        if candidates:
            winner = min(candidates, key=lambda item: item["claim_id"])
            matched_claims[fact["fact_id"]] = winner["claim_id"]
            matched_states[fact["fact_id"]] = winner["state"]
    matched_ids = [fact["fact_id"] for fact in manifest["gold_facts"] if fact["fact_id"] in matched_claims]
    missing_ids = [fact["fact_id"] for fact in manifest["gold_facts"] if fact["fact_id"] not in matched_claims]
    matched_weight = sum(facts_by_id[fact_id]["weight"] for fact_id in matched_ids)
    total_weight = sum(fact["weight"] for fact in manifest["gold_facts"])

    contradiction_rules = {rule["rule_id"]: rule for rule in manifest["critical_contradictions"]}
    failures: set[str] = set()
    for claim in claims:
        if claim["predicate_id"] in contradiction_rules and claim["polarity"] in contradiction_rules[claim["predicate_id"]]["forbidden_polarities"]:
            failures.add(claim["predicate_id"])
        fact = facts_by_id.get(claim["predicate_id"])
        if fact and fact["critical"] and claim["polarity"] == "negated":
            failures.add(f"DENY_{fact['fact_id']}")
    safety = unsafe_findings(response, "response")
    if safety:
        failures.add("SAFETY")
    auto_failure = bool(failures)
    hard_score = 0.0 if auto_failure else round(100 * matched_weight / total_weight, 6)
    critical_missing = [
        fact["fact_id"] for fact in manifest["gold_facts"] if fact["critical"] and fact["fact_id"] not in matched_claims
    ]
    return {
        "blind_label": f"run-{run_index:03d}",
        "hard_score": hard_score,
        "eligible": not auto_failure and not critical_missing,
        "auto_failure": auto_failure,
        "failure_reasons": sorted(failures),
        "critical_facts_missing": critical_missing,
        "gold": {
            "algorithm": "structured_predicate_all_support_groups_v2",
            "matched_fact_ids": matched_ids,
            "missing_fact_ids": missing_ids,
            "matched_weight": matched_weight,
            "total_weight": total_weight,
            "matched_claim_ids": matched_claims,
            "matched_states": matched_states,
        },
        "hard_metrics": {
            "evidence_weighted_gold_percent": hard_score,
            "strict_schema": "gate_passed",
            "complete_dispositions": "gate_passed",
            "resolved_citations": "gate_passed",
            "safety": "gate_failed" if safety else "gate_passed",
            "critical_state_honesty": "gate_failed" if failures - {"SAFETY"} else "gate_passed",
        },
    }


def validate_blinded_review(
    value: Any,
    manifest: dict[str, Any],
    bundle: dict[str, Any],
    response_hashes: list[str],
) -> dict[str, Any]:
    review = require_object(value, "blinded review")
    exact_keys(
        review,
        {"schema_version", "kind", "corpus_sha256", "bundle_sha256", "response_sha256s", "candidate_label", "reviews"},
        "blinded review",
    )
    if review["schema_version"] != 1 or review["kind"] != "session_bakeoff_blinded_review":
        fail("unsupported blinded-review contract")
    if review["corpus_sha256"] != manifest["manifest_sha256"] or review["bundle_sha256"] != bundle["bundle_sha256"] or review["response_sha256s"] != response_hashes:
        fail("blinded review does not bind the exact three response runs")
    if not BLIND_CANDIDATE_RE.fullmatch(require_string(review["candidate_label"], "candidate blind label", 64)):
        fail("candidate label is not opaque")
    reviews = require_list(review["reviews"], "blinded reviewer results")
    if not 1 <= len(reviews) <= MAX_REVIEWERS:
        fail("blinded review requires 1-10 reviewers")
    reviewers: set[str] = set()
    for reviewer in reviews:
        exact_keys(require_object(reviewer, "reviewer result"), {"reviewer_label", "run_scores"}, "reviewer result")
        label = require_string(reviewer["reviewer_label"], "reviewer blind label", 64)
        if not BLIND_REVIEWER_RE.fullmatch(label) or label in reviewers:
            fail("reviewer labels must be unique and opaque")
        reviewers.add(label)
        run_scores = require_list(reviewer["run_scores"], "reviewer run scores")
        if [row.get("blind_label") if isinstance(row, dict) else None for row in run_scores] != ["run-001", "run-002", "run-003"]:
            fail("every reviewer must score all three blinded runs exactly once")
        for run_score in run_scores:
            exact_keys(require_object(run_score, "review run score"), {"blind_label", "dimensions"}, "review run score")
            dimensions = require_list(run_score["dimensions"], "review dimensions")
            if [row.get("dimension") if isinstance(row, dict) else None for row in dimensions] != RUBRIC_DIMENSIONS:
                fail("review dimensions must use the frozen order and complete set")
            for dimension in dimensions:
                exact_keys(require_object(dimension, "review dimension"), {"dimension", "points"}, "review dimension")
                require_integer(dimension["points"], "review dimension points", 0, 5)
    assert_safe(review, "blinded review")
    return review


def qualitative_scores(review: dict[str, Any]) -> list[float]:
    per_run: list[float] = []
    for run_index in range(REQUIRED_REPEATS):
        totals = [
            sum(row["points"] for row in reviewer["run_scores"][run_index]["dimensions"])
            for reviewer in review["reviews"]
        ]
        per_run.append(round(100 * float(median(totals)) / 45, 6))
    return per_run


def consistency_score(runs: list[dict[str, Any]], manifest: dict[str, Any]) -> float:
    stable_weight = 0
    for fact in manifest["gold_facts"]:
        fact_id = fact["fact_id"]
        states = [run["gold"]["matched_states"].get(fact_id) for run in runs]
        if all(state is not None for state in states) and len(set(states)) == 1:
            stable_weight += fact["weight"]
    return round(100 * stable_weight / 54, 6)


def aggregate_scores(
    runs: list[dict[str, Any]], qualitative: list[float], manifest: dict[str, Any]
) -> dict[str, Any]:
    if len(runs) != REQUIRED_REPEATS or len(qualitative) != REQUIRED_REPEATS:
        fail("exactly three runs are mandatory; no best-run selection is allowed")
    hard = [float(run["hard_score"]) for run in runs]
    median_hard = float(median(hard))
    worst_hard = min(hard)
    median_qualitative = float(median(qualitative))
    consistency = consistency_score(runs, manifest)
    composite = round(
        0.50 * median_hard
        + 0.20 * worst_hard
        + 0.20 * median_qualitative
        + 0.10 * consistency,
        6,
    )
    return {
        "repeat_count": 3,
        "hard_scores": hard,
        "median_hard_score": round(median_hard, 6),
        "worst_hard_score": round(worst_hard, 6),
        "blinded_qualitative_scores": qualitative,
        "median_blinded_qualitative_score": round(median_qualitative, 6),
        "repeat_consistency_score": consistency,
        "final_composite_score": composite,
        "formula": "0.50*median_hard + 0.20*worst_hard + 0.20*median_blinded_qualitative + 0.10*repeat_consistency",
        "all_runs_eligible": all(run["eligible"] for run in runs),
        "aggregation_policy": "all three runs are mandatory; no run is selected or discarded",
    }


def validate_vision_probe(value: Any) -> dict[str, Any]:
    vision = require_object(value, "vision probe")
    exact_keys(
        vision,
        {"fixture_id", "image_sha256", "stop_reason", "observed", "matched_fact_ids", "missing_fact_ids", "score", "maximum_score", "passed", "cleanup_boundary"},
        "vision probe",
    )
    if vision["fixture_id"] != "synthetic-ui-canary-v1" or vision["image_sha256"] != SYNTHETIC_VISION_SHA256 or vision["stop_reason"] != "eosFound" or vision["cleanup_boundary"] != "client_async_dispose_completed":
        fail("vision probe binding, stop, or cleanup boundary changed")
    observed = require_object(vision["observed"], "vision observation")
    exact_keys(observed, set(SYNTHETIC_VISION_GOLD), "vision observation")
    vocabularies = {
        "top_bar_present": {True, False},
        "left_sidebar_present": {True, False},
        "main_panel_present": {True, False},
        "status_text": {"ERR", "OK", "WARN", "NONE", "UNREADABLE"},
        "status_state": {"error", "ready", "warning", "none", "unreadable"},
        "anomaly_color": {"rose", "cyan", "gray", "none", "unreadable"},
        "anomaly_position": {"upper_right", "upper_left", "lower_right", "lower_left", "none", "unreadable"},
        "anomaly_shape": {"square", "circle", "triangle", "none", "unreadable"},
    }
    if any(observed[key] not in vocabulary for key, vocabulary in vocabularies.items()):
        fail("vision observation is outside its finite vocabulary")
    matched = [f"V{index:02d}" for index, (key, gold) in enumerate(SYNTHETIC_VISION_GOLD.items(), 1) if observed[key] == gold]
    missing = [f"V{index:02d}" for index, (key, gold) in enumerate(SYNTHETIC_VISION_GOLD.items(), 1) if observed[key] != gold]
    if vision["matched_fact_ids"] != matched or vision["missing_fact_ids"] != missing or vision["score"] != len(matched) or vision["maximum_score"] != 8 or vision["passed"] is not (not missing):
        fail("vision probe exact-gold score changed")
    return vision


def validate_callback_result(value: Any, bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    callback = require_object(value, "callback result")
    exact_keys(
        callback,
        {"schema_version", "kind", "tool_version", "corpus_sha256", "bundle_sha256", "ranking_status", "evaluation_limitations", "input_hashes", "lifecycle_binding", "sdk", "inference", "repeat_runs", "result_sha256"},
        "callback result",
    )
    if callback["schema_version"] != 2 or callback["kind"] != "session_bakeoff_callback_result" or callback["tool_version"] != "lmstudio-session-bakeoff-callback-v2":
        fail("unsupported callback result contract")
    if callback["corpus_sha256"] != bundle["corpus_sha256"] or callback["bundle_sha256"] != bundle["bundle_sha256"] or callback["ranking_status"] != "provisional_visual_evidence" or callback["evaluation_limitations"] != bundle["evaluation_limitations"]:
        fail("callback result binding changed")
    declared = require_sha(callback["result_sha256"], "callback result sha256")
    unsigned = dict(callback)
    unsigned.pop("result_sha256")
    if sha256_value(unsigned) != declared:
        fail("callback result seal changed")
    hashes = require_object(callback["input_hashes"], "callback input hashes")
    exact_keys(hashes, {"bundle_file_sha256", "binding_file_sha256", "sdk_entry_sha256", "sdk_closure_sha256", "sdk_dependency_closure_sha256", "python_preflight_receipt_sha256"}, "callback input hashes")
    for key, digest in hashes.items():
        require_sha(digest, f"callback {key}")
    sdk = require_object(callback["sdk"], "callback sdk")
    exact_keys(sdk, {"name", "version"}, "callback sdk")
    if sdk != {"name": "@lmstudio/sdk", "version": "1.5.0"}:
        fail("callback SDK identity changed")
    lifecycle = require_object(callback["lifecycle_binding"], "callback lifecycle binding")
    exact_keys(lifecycle, {"identifier", "model_key", "selected_variant", "profile", "instance_reference", "indexed_model_identifier", "context_length", "snapshot_sha256", "load_config_sha256", "process_token_sha256", "endpoint_sha256"}, "callback lifecycle binding")
    for key in ("identifier", "model_key", "selected_variant", "profile", "instance_reference", "indexed_model_identifier"):
        require_string(lifecycle[key], f"callback lifecycle {key}", 2048)
    require_integer(lifecycle["context_length"], "callback context", TARGET_CONTEXT_TOKENS, 10_000_000)
    for key in ("snapshot_sha256", "load_config_sha256", "process_token_sha256", "endpoint_sha256"):
        require_sha(lifecycle[key], f"callback lifecycle {key}")
    inference = require_object(callback["inference"], "callback inference")
    exact_keys(inference, {"deadline_ms", "repeat_count", "packet_call_count", "maximum_inference_call_count", "max_tokens", "reasoning_budget", "temperature", "seed_policy", "context_overflow_policy", "target_context_tokens", "reserved_context_tokens", "conservative_input_token_limit", "vision_probe"}, "callback inference")
    require_integer(inference["deadline_ms"], "callback deadline", 1000, MAX_CALLBACK_DEADLINE_MS)
    if inference["repeat_count"] != 3 or inference["packet_call_count"] != 24 or inference["maximum_inference_call_count"] != 25 or inference["temperature"] != 0 or inference["seed_policy"] != "per_request_seed_unavailable_sdk_1_5_0" or inference["context_overflow_policy"] != "stopAtLimit" or inference["target_context_tokens"] != TARGET_CONTEXT_TOKENS or inference["reserved_context_tokens"] != RESERVED_CONTEXT_TOKENS or inference["conservative_input_token_limit"] != MAX_CONSERVATIVE_INPUT_TOKENS:
        fail("callback inference contract changed")
    require_integer(inference["max_tokens"], "callback output tokens", 1024, MAX_OUTPUT_TOKENS)
    require_integer(inference["reasoning_budget"], "callback reasoning tokens", 0, MAX_REASONING_TOKENS)
    vision = validate_vision_probe(inference["vision_probe"])
    repeats = require_list(callback["repeat_runs"], "callback repeats")
    if len(repeats) != 3:
        fail("callback must preserve all three repeats")
    canonical_order = [packet["packet_id"] for packet in bundle["packets"]]
    responses: list[dict[str, Any]] = []
    for index, repeat in enumerate(repeats, 1):
        exact_keys(require_object(repeat, "callback repeat"), {"repeat_index", "packet_order", "packet_runs", "response"}, "callback repeat")
        offset = PACKET_ROTATION_OFFSETS[index - 1]
        expected_order = canonical_order[offset:] + canonical_order[:offset]
        if repeat["repeat_index"] != index or repeat["packet_order"] != expected_order:
            fail("callback repeat order changed")
        packet_runs = require_list(repeat["packet_runs"], "callback packet runs")
        if len(packet_runs) != 8:
            fail("callback packet-run count changed")
        for packet_id, packet_run in zip(expected_order, packet_runs, strict=True):
            exact_keys(require_object(packet_run, "callback packet run"), {"packet_id", "semantic_unit_count", "canonical_packet_bytes", "canonical_packet_characters", "formatted_prompt_tokens", "schema_utf8_bytes_as_token_upper_bound", "conservative_input_tokens", "stop_reason"}, "callback packet run")
            packet = next(row for row in bundle["packets"] if row["packet_id"] == packet_id)
            if packet_run["packet_id"] != packet_id or packet_run["semantic_unit_count"] != len(packet["input_units"]) or packet_run["canonical_packet_bytes"] != packet["canonical_packet_bytes"] or packet_run["canonical_packet_characters"] != packet["canonical_packet_characters"] or packet_run["stop_reason"] != "eosFound":
                fail("callback packet attestation changed")
            formatted = require_integer(packet_run["formatted_prompt_tokens"], "formatted prompt tokens", 1, MAX_CONSERVATIVE_INPUT_TOKENS)
            schema_tokens = require_integer(packet_run["schema_utf8_bytes_as_token_upper_bound"], "schema token bound", 1, MAX_CONSERVATIVE_INPUT_TOKENS)
            if packet_run["conservative_input_tokens"] != formatted + schema_tokens or packet_run["conservative_input_tokens"] > MAX_CONSERVATIVE_INPUT_TOKENS:
                fail("callback conservative token bound changed")
        response = validate_response(repeat["response"], bundle)
        if [row["packet_id"] for row in response["packet_results"]] != expected_order:
            fail("callback response does not preserve rotated order")
        responses.append(response)
    return responses, vision


def preflight_receipt(
    corpus: Path,
    bundle_path: Path,
    prepared_workdir: Path,
    corroborating_log: Path,
    validator: Path,
) -> dict[str, Any]:
    manifest, _ = load_manifest(corpus)
    bundle_value, _ = read_json(bundle_path, "bake-off bundle")
    bundle = validate_bundle(bundle_value, manifest)
    rebuilt = build_bundle(corpus, prepared_workdir, corroborating_log, validator)
    if rebuilt != bundle:
        fail("bundle cannot be reconstructed from the bound prepared-v4 closure")
    receipt = {
        "schema_version": 1,
        "kind": "session_bakeoff_preflight_receipt",
        "validated": True,
        "corpus_sha256": manifest["manifest_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
        "prepared_binding_sha256": sha256_value(bundle["prepared_binding"]),
        "redaction_contract": REDACTION_CONTRACT,
        "safety_contract": "strict_keys_and_v6_defense_in_depth-v1",
    }
    receipt["receipt_sha256"] = sha256_value(receipt)
    return receipt


def command_validate_manifest(args: argparse.Namespace) -> None:
    manifest, _ = load_manifest(args.corpus)
    print(json.dumps({"ok": True, "manifest_sha256": manifest["manifest_sha256"]}, sort_keys=True))


def command_build(args: argparse.Namespace) -> None:
    bundle = build_bundle(args.corpus, args.prepared_workdir, args.corroborating_log, args.validator)
    write_json(args.output, bundle)
    print(json.dumps({"ok": True, "bundle_sha256": bundle["bundle_sha256"]}, sort_keys=True))


def command_preflight(args: argparse.Namespace) -> None:
    receipt = preflight_receipt(args.corpus, args.bundle, args.prepared_workdir, args.corroborating_log, args.validator)
    print(canonical_bytes(receipt).decode("utf-8"))


def command_score(args: argparse.Namespace) -> None:
    manifest, _ = load_manifest(args.corpus)
    bundle_value, _ = read_json(args.bundle, "bake-off bundle")
    bundle = validate_bundle(bundle_value, manifest)
    if len(args.response) not in {1, 3}:
        fail("score input must be one three-repeat callback or exactly three bare responses")
    responses: list[dict[str, Any]] = []
    response_hashes: list[str] = []
    source_hashes: list[str] = []
    vision: dict[str, Any] = {
        "status": "not_provided",
        "passed": False,
        "score": 0,
        "maximum_score": 8,
        "repeatability_tested": False,
    }
    if len(args.response) == 1:
        value, raw = read_json(args.response[0], "score artifact", limit=4 * 1024 * 1024)
        source_hashes.append(sha256_bytes(raw))
        if not isinstance(value, dict) or value.get("kind") != "session_bakeoff_callback_result":
            fail("a single score artifact must be a three-repeat callback result")
        responses, observed_vision = validate_callback_result(value, bundle)
        vision = {"status": "scored", **observed_vision, "repeatability_tested": False}
    else:
        for index, path in enumerate(args.response, 1):
            value, raw = read_json(path, f"response {index}", limit=4 * 1024 * 1024)
            source_hashes.append(sha256_bytes(raw))
            responses.append(validate_response(value, bundle))
    if len(responses) != 3:
        fail("exactly three response runs are mandatory")
    response_hashes = [sha256_value(response) for response in responses]
    review_value, review_raw = read_json(args.blinded_review, "blinded review", limit=2 * 1024 * 1024)
    review = validate_blinded_review(review_value, manifest, bundle, response_hashes)
    runs = [score_response(response, manifest, bundle, index) for index, response in enumerate(responses, 1)]
    if vision["status"] == "scored" and not vision["passed"]:
        for run in runs:
            run["hard_score"] = 0.0
            run["eligible"] = False
            run["auto_failure"] = True
            run["failure_reasons"] = sorted({*run["failure_reasons"], "VISION_GATE"})
            run["hard_metrics"]["synthetic_vision_gate"] = "gate_failed"
    qualitative = qualitative_scores(review)
    aggregate = aggregate_scores(runs, qualitative, manifest)
    aggregate["vision_gate_passed"] = vision["status"] == "scored" and vision["passed"]
    aggregate["ranking_eligible"] = aggregate["all_runs_eligible"] and aggregate["vision_gate_passed"]
    output: dict[str, Any] = {
        "schema_version": 2,
        "kind": "session_bakeoff_score",
        "tool_version": TOOL_VERSION,
        "corpus_sha256": manifest["manifest_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
        "response_sha256s": response_hashes,
        "source_artifact_sha256s": source_hashes,
        "blinded_review_sha256": sha256_bytes(review_raw),
        "candidate_label": review["candidate_label"],
        "ranking_status": "provisional_visual_evidence",
        "evaluation_limitations": manifest["evaluation_limitations"],
        "vision_gate": vision,
        "runs": runs,
        "aggregate": aggregate,
    }
    assert_safe(output, "score output")
    output["score_sha256"] = sha256_value(output)
    write_json(args.output, output)
    print(json.dumps({"ok": True, "score_sha256": output["score_sha256"]}, sort_keys=True))


def default_validator() -> Path:
    return Path(__file__).resolve().with_name("session-deep-dive.py")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-manifest")
    validate.add_argument("--corpus", type=Path, required=True)
    validate.set_defaults(handler=command_validate_manifest)
    build = commands.add_parser("build")
    build.add_argument("--corpus", type=Path, required=True)
    build.add_argument("--prepared-workdir", type=Path, required=True)
    build.add_argument("--corroborating-log", type=Path, required=True)
    build.add_argument("--validator", type=Path, default=default_validator())
    build.add_argument("--output", type=Path, required=True)
    build.set_defaults(handler=command_build)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--corpus", type=Path, required=True)
    preflight.add_argument("--bundle", type=Path, required=True)
    preflight.add_argument("--prepared-workdir", type=Path, required=True)
    preflight.add_argument("--corroborating-log", type=Path, required=True)
    preflight.add_argument("--validator", type=Path, default=default_validator())
    preflight.set_defaults(handler=command_preflight)
    score = commands.add_parser("score")
    score.add_argument("--corpus", type=Path, required=True)
    score.add_argument("--bundle", type=Path, required=True)
    score.add_argument("--response", type=Path, action="append", required=True)
    score.add_argument("--blinded-review", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    score.set_defaults(handler=command_score)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        args.handler(args)
        return 0
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
