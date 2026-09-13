"""Declarative PR-report manifest, evidence graph, readiness, and export primitives."""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "pr-reports/schema/sections.json"
PRIVATE_PATTERNS = {
    "absolute user path": re.compile(r"/(?:Users|home)/[^\s<>'\"]+"),
    "session identifier": re.compile(r"\b(?:session[_ -]?id|sess(?:ion)?-)[\w-]+", re.I),
    "private IPv4": re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
    "secret-like assignment": re.compile(r"\b(?:token|secret|password|api[_-]?key)\s*[:=]\s*[^\s<]+", re.I),
    "private URL": re.compile(r"https?://(?:localhost|[^/\s]+\.(?:local|internal))\b", re.I),
}


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    registry = json.loads(path.read_text())
    flattened = [section for stage in registry["stages"] for section in stage["sections"]]
    if len(flattened) != 29 or len(set(flattened)) != 29:
        raise ValueError("section registry must contain exactly 29 unique sections")
    if set(flattened) != set(registry["sections"]):
        raise ValueError("stage and section registry denominators differ")
    return registry


def read_meta(source: str) -> dict[str, str]:
    return dict(re.findall(r'<meta name="artifact\.([^"]+)" content="([^"]*)">', source))


def details_blocks(source: str) -> dict[str, str]:
    return {match.group(1): match.group(0) for match in re.finditer(
        r'<details id="([^"]+)".*?</details>', source, re.S)}


def section_state(block: str) -> str:
    own = re.search(r'<details[^>]*\sdata-state="([^"]+)"', block)
    if own:
        return own.group(1)
    values = re.findall(r'data-state="([^"]+)"', block)
    for state in ("FAIL", "BLOCKED", "STALE", "NOT RUN", "UNKNOWN"):
        if state in values:
            return state
    if values and all(value == "NOT APPLICABLE" for value in values):
        return "NOT APPLICABLE"
    return "PASS" if values and all(value == "PASS" for value in values) else "UNKNOWN"


def evidence_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def referenced_ids(block: str) -> list[str]:
    values = []
    for refs in re.findall(r'data-ref-ids="([^"]+)"', block):
        values.extend(refs.split())
    return sorted(set(values))


def record_type(record: dict) -> str:
    explicit = record.get("evidence_type")
    if explicit:
        return explicit
    if record.get("kind") in {"url", "documentation", "external"}:
        return "live-reference"
    if record.get("kind") in {"human-audit", "public-audit", "observation"}:
        return "human-observation"
    return "reproducible-command" if record.get("command") else "immutable-snapshot"


def build_manifest(report: Path, registry_path: Path = REGISTRY_PATH) -> dict:
    source = report.read_text()
    digest_source = re.sub(r'\n?<script id="pr-report-manifest" type="application/json">.*?</script>', "", source, flags=re.S)
    digest_source = re.sub(
        r'(<meta name="artifact\.(?:report-digest|evidence-manifest-digest)" content=")[^"]*(">)',
        r'\1UNSEALED\2', digest_source,
    )
    meta = read_meta(source)
    registry = load_registry(registry_path)
    blocks = details_blocks(source)
    evidence_path = Path(html.unescape(meta.get("evidence-manifest", "")))
    records = evidence_records(evidence_path)
    by_id = {record.get("id"): record for record in records}
    stages, claims, dangling = [], [], []
    for stage in registry["stages"]:
        section_rows = []
        for section_id in stage["sections"]:
            block = blocks.get(section_id, "")
            refs = referenced_ids(block)
            missing = [ref for ref in refs if ref.startswith("E-") and ref not in by_id]
            dangling.extend({"section": section_id, "evidence": ref} for ref in missing)
            section_rows.append({
                "id": section_id,
                "state": section_state(block),
                "evidence": refs,
                **registry["sections"][section_id],
            })
            for claim_id, state, claim_refs in re.findall(
                r'data-record-id="(CLM-\d+)"[^>]*data-state="([^"]+)"[^>]*data-ref-ids="([^"]*)"', block):
                claims.append({"id": claim_id, "section": section_id, "state": state,
                               "evidence": claim_refs.split()})
        stages.append({"id": stage["id"], "label": stage["label"], "sections": section_rows})
    used = set(ref for stage in stages for section in stage["sections"] for ref in section["evidence"])
    evidence = [{**record, "evidence_type": record_type(record),
                 "record_digest": sha256_bytes(canonical_json(record).encode()),
                 "used": record.get("id") in used} for record in records]
    states = [section["state"] for stage in stages for section in stage["sections"]]
    unresolved = sum(state not in {"PASS", "NOT APPLICABLE"} for state in states)
    readiness = {
        "sections": {"satisfied": len(states) - unresolved, "total": len(states)},
        "claims": {"supported": sum(bool(claim["evidence"]) for claim in claims), "total": len(claims)},
        "evidence": {"used": sum(record["used"] for record in evidence), "total": len(evidence)},
        "blocking_states": sorted({state for state in states if state in {"FAIL", "BLOCKED", "STALE"}}),
    }
    acknowledgement_path = report.with_suffix(".review.jsonl")
    acknowledgements = evidence_records(acknowledgement_path)
    report_head = meta.get("head", "").split("@")[-1].strip()
    current_report_digest = sha256_bytes(digest_source.encode())
    for acknowledgement in acknowledgements:
        acknowledgement["current"] = (
            acknowledgement.get("head_sha") == report_head
            and acknowledgement.get("report_sha256") == current_report_digest
        )
    acknowledged = {item.get("checkpoint") for item in acknowledgements if item.get("current")}
    readiness["review_checkpoints"] = {
        "acknowledged": len(acknowledged),
        "total": len(registry["review_checkpoints"]),
        "stale": sum(not item.get("current") for item in acknowledgements),
    }
    manifest = {
        "manifest_schema": 1,
        "generated_at": meta.get("updated", meta.get("date", "unknown")),
        "report": str(report.resolve()),
        "report_sha256": current_report_digest,
        "identity": {key: html.unescape(value) for key, value in meta.items() if key not in {
            "report-digest", "evidence-manifest-digest"}},
        "stages": stages,
        "claims": claims,
        "evidence": evidence,
        "review_acknowledgements": acknowledgements,
        "graph_issues": {
            "dangling_references": dangling,
            "unused_evidence": [record.get("id") for record in evidence if not record["used"]],
            "unsupported_claims": [claim["id"] for claim in claims if not claim["evidence"]],
        },
        "readiness": readiness,
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(manifest).encode())
    return manifest


def embed_manifest(source: str, manifest: dict) -> str:
    payload = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    tag = f'<script id="pr-report-manifest" type="application/json">{payload}</script>'
    pattern = re.compile(r'<script id="pr-report-manifest" type="application/json">.*?</script>', re.S)
    if pattern.search(source):
        return pattern.sub(tag, source, count=1)
    return source.replace("</body>", tag + "\n</body>", 1)


def public_summary(source: str) -> str:
    match = re.search(r'<details id="public-summary".*?</details>', source, re.S)
    if not match:
        raise ValueError("public-summary section is missing")
    block = re.sub(r'\sdata-public-[\w-]+="[^"]*"', "", match.group(0))
    block = re.sub(r'\sdata-ref-ids="[^"]*"|\sdata-state="[^"]*"|\sdata-reason="[^"]*"', "", block)
    return block


def scan_public(value: str) -> list[dict]:
    return [{"kind": kind, "match": match.group(0)} for kind, pattern in PRIVATE_PATTERNS.items()
            for match in pattern.finditer(value)]


def semantic_snapshot(manifest: dict) -> dict:
    return {
        "identity": manifest["identity"],
        "sections": {section["id"]: {"state": section["state"], "evidence": section["evidence"]}
                     for stage in manifest["stages"] for section in stage["sections"]},
        "claims": {claim["id"]: claim for claim in manifest["claims"]},
        "evidence": {record["id"]: record["record_digest"] for record in manifest["evidence"]},
        "readiness": manifest["readiness"],
    }


def semantic_diff(before: dict, after: dict) -> dict:
    result = {}
    for field in ("identity", "sections", "claims", "evidence", "readiness"):
        left, right = before.get(field, {}), after.get(field, {})
        if isinstance(left, dict) and isinstance(right, dict):
            result[field] = {
                "added": {key: right[key] for key in right.keys() - left.keys()},
                "removed": {key: left[key] for key in left.keys() - right.keys()},
                "changed": {key: {"before": left[key], "after": right[key]}
                            for key in left.keys() & right.keys() if left[key] != right[key]},
            }
    return result


@dataclass(frozen=True)
class DriftResult:
    stale: list[str]
    observed: dict[str, str]


def detect_drift(manifest: dict, *, head: str | None, merge_base: str | None,
                 changed_files_digest: str | None = None) -> DriftResult:
    identity = manifest["identity"]
    recorded_head = identity.get("head", "").split("@")[-1].strip()
    recorded_merge = identity.get("merge-base", "").strip()
    stale, observed = [], {}
    if head:
        observed["head"] = head
        if recorded_head.lower() != head.lower():
            stale.append("head")
    if merge_base:
        observed["merge-base"] = merge_base
        if recorded_merge.lower() != merge_base.lower():
            stale.append("merge-base")
    if changed_files_digest:
        observed["changed-files-digest"] = changed_files_digest
        if identity.get("changed-files-digest") != changed_files_digest:
            stale.append("changed-files")
    return DriftResult(sorted(stale), observed)
