#!/usr/bin/env python3
"""Validate PR report structure, integrity, evidence, and optional live-head inputs."""
from __future__ import annotations

import argparse
import html
import hashlib
import json
import re
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from _app import validate  # noqa: E402
from _app.pr_reports import STATES  # noqa: E402
from _app.pr_manifest import locked  # noqa: E402

REPORT_DIGEST = re.compile(r'(<meta name="artifact\.report-digest" content=")[^"]*(">)')
MANIFEST_DIGEST = re.compile(r'(<meta name="artifact\.evidence-manifest-digest" content=")[^"]*(">)')


def report_digest(source: str) -> str:
    normalized, count = REPORT_DIGEST.subn(r"\1UNSEALED\2", source, count=1)
    if count != 1:
        return ""
    return hashlib.sha256(normalized.encode()).hexdigest()


def check_manifest(path: Path, expected_head: str) -> tuple[list[str], list[dict]]:
    errors, ids, records = [], set(), []
    if not path.is_file():
        return ["evidence manifest does not exist: " + str(path)], records
    required = {"id", "kind", "path", "sha256", "bytes", "producer", "command",
                "cwd", "source_sha", "state", "applies_to", "reason", "captured_at"}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"manifest line {number}: {error}")
            continue
        records.append(record)
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"manifest line {number} missing: {', '.join(missing)}")
            continue
        evidence_id = record.get("id")
        if not re.fullmatch(r"E-\d{3,}", str(evidence_id)):
            errors.append("invalid evidence ID: " + str(evidence_id))
        if evidence_id in ids:
            errors.append("duplicate evidence ID: " + str(evidence_id))
        ids.add(evidence_id)
        target = Path(record.get("path", ""))
        if not target.is_absolute():
            errors.append("evidence path is not absolute for " + str(evidence_id))
        if target.resolve() == path.resolve():
            errors.append("manifest cannot be its own evidence: " + str(evidence_id))
        if not target.is_file():
            errors.append("missing evidence file for " + str(evidence_id) + ": " + str(target))
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != record.get("sha256"):
            errors.append("digest mismatch for " + str(evidence_id))
        if target.stat().st_size != record.get("bytes"):
            errors.append("byte count mismatch for " + str(evidence_id))
        if record.get("state") not in STATES:
            errors.append("invalid evidence state for " + str(evidence_id))
        if record.get("evidence_type", "immutable-snapshot") not in {
                "immutable-snapshot", "reproducible-command", "human-observation",
                "inference", "live-reference", "unverified-assertion"}:
            errors.append("invalid evidence type for " + str(evidence_id))
        if record.get("state") != "PASS" and not str(record.get("reason", "")).strip():
            errors.append("non-PASS evidence has no reason: " + str(evidence_id))
        if record.get("applies_to") not in {"base", "head", "environment", "external"}:
            errors.append("invalid applies_to for " + str(evidence_id))
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get("source_sha", ""))):
            errors.append("invalid source SHA for " + str(evidence_id))
        if not Path(str(record.get("cwd", ""))).is_absolute():
            errors.append("cwd is not absolute for " + str(evidence_id))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})",
                            str(record.get("captured_at", ""))):
            errors.append("invalid capture timestamp for " + str(evidence_id))
        if (expected_head and record.get("applies_to") == "head"
                and record.get("source_sha") != expected_head and record.get("state") == "PASS"):
            errors.append("STALE evidence " + str(evidence_id) + " covers "
                          + str(record.get("source_sha")) + ", not current head")
    return errors, records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--current-head", help="Current PR head SHA for staleness checking")
    parser.add_argument("--current-merge-base", help="Current merge-base SHA")
    parser.add_argument("--changed-files", type=Path, help="Newline list used to check the file map")
    from _app.projects import library_root
    parser.add_argument("--root", type=Path, default=library_root())
    parser.add_argument("--canonical-path", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--allow-unsealed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    report = args.report.resolve()
    source = report.read_text()
    root = args.root.resolve()
    identity_path = args.canonical_path.resolve() if args.canonical_path else report
    try:
        rel = identity_path.relative_to(root).as_posix()
    except ValueError:
        parser.error("report must live under the artifact package")
    order_path = root / "index-meta.json"
    order = json.loads(order_path.read_text()).get("order", []) if order_path.exists() else []
    from _app.projects import template_path, brand_for
    meta = validate.read_meta(source)
    template = template_path("pr-reports", brand_for(meta.get("repository", "unraid/core"), unraid_related=meta.get("unraid-related")=="true")).read_text()
    parts = Path(rel).parts
    check_rel = "pr-reports/"+parts[0]+"/"+parts[2] if len(parts)==3 and parts[1]=="pr-reports" else rel
    issues = validate.validate_artifact(root, check_rel, source, order, template)
    errors = [item["rule"] + ": " + item["message"]
              for item in issues if item["severity"] == "error"]
    meta = validate.read_meta(source)
    duplicate_paths = []
    for candidate in root.rglob("*.html"):
        if candidate.resolve() in {identity_path, report}: continue
        try: candidate_meta = validate.read_meta(candidate.read_text(errors="replace"))
        except OSError: continue
        if meta.get("id") and candidate_meta.get("id") == meta.get("id"):
            duplicate_paths.append(candidate.relative_to(root).as_posix())
    if duplicate_paths: errors.append("duplicate artifact.id also used by: " + ", ".join(sorted(duplicate_paths)))
    for related in [value.strip() for value in meta.get("related", "").split(",")
                    if value.strip() and value.strip().lower() not in {"none", "not applicable"}]:
        if not (root / related).exists(): errors.append("related artifact does not exist: " + related)
    recorded_head = meta.get("head", "").split("@")[-1].strip().lower()
    if args.current_head and args.current_head.lower() != recorded_head:
        errors.append("STALE: current head differs from artifact.head")
    recorded_merge = meta.get("merge-base", "").lower()
    if args.current_merge_base and args.current_merge_base.lower() != recorded_merge:
        errors.append("STALE: current merge base differs from artifact.merge-base")
    manifest = Path(html.unescape(meta.get("evidence-manifest", "")))
    with locked(manifest):
        manifest_errors, records = check_manifest(
            manifest, args.current_head.lower() if args.current_head else "")
        manifest_bytes = manifest.read_bytes() if manifest.is_file() else b""
    errors.extend(manifest_errors)
    html_evidence = set(re.findall(r'data-record-id="(E-\d{3,})"', source))
    manifest_evidence = {str(record.get("id")) for record in records}
    if html_evidence != manifest_evidence:
        errors.append("HTML evidence ledger and manifest IDs differ: html="
                      + str(sorted(html_evidence)) + " manifest=" + str(sorted(manifest_evidence)))
    rendered_digests = dict(re.findall(r'data-record-id="(E-\d{3,})"[^>]*data-record-digest="([0-9a-f]{64})"', source))
    authoritative_digests = {str(record.get("id")): hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for record in records}
    if records and rendered_digests != authoritative_digests:
        errors.append("rendered evidence ledger differs from manifest records")
    sealed = meta.get("report-digest", "")
    if sealed not in ("", "UNSEALED") and sealed != report_digest(source):
        errors.append("report digest mismatch")
    manifest_sealed = meta.get("evidence-manifest-digest", "")
    actual_manifest_digest = hashlib.sha256(manifest_bytes).hexdigest() if manifest_bytes else ""
    if manifest_sealed not in ("", "UNSEALED") and manifest_sealed != actual_manifest_digest:
        errors.append("evidence manifest digest mismatch")
    worktree = Path(meta.get("worktree", ""))
    base_sha = meta.get("base", "").split("@")[-1].strip()
    derived_files = set()
    derivation_succeeded = False
    if worktree.is_dir() and base_sha and recorded_head:
        diff = subprocess.run(["git", "-C", str(worktree), "diff", "--name-only", "-z",
                               base_sha + "..." + recorded_head], capture_output=True, check=False)
        if diff.returncode == 0:
            derived_files = {part.decode() for part in diff.stdout.split(b"\0") if part}
            derivation_succeeded = True
        else: errors.append("cannot derive changed-file denominator from Git")
    if args.changed_files:
        imported_files = {line.strip() for line in args.changed_files.read_text().splitlines() if line.strip()}
        if derivation_succeeded and imported_files != derived_files:
            errors.append("imported changed-file inventory differs from Git denominator")
    if derivation_succeeded:
        expected_files = derived_files
        recorded_files = set(re.findall(r'data-file="([^"]+)"', source))
        if expected_files != recorded_files:
            errors.append("file map differs: missing=" + str(sorted(expected_files-recorded_files))
                          + " extra=" + str(sorted(recorded_files-expected_files)))
    if meta.get("status") == "accepted":
        if not derivation_succeeded:
            errors.append("accepted validation requires successful Git changed-file derivation")
        if not args.current_head or not args.current_merge_base or not args.changed_files:
            errors.append("accepted validation requires --current-head, --current-merge-base, and --changed-files")
        snapshots = [r for r in records if r.get("kind") == "pr-state" and r.get("state") == "PASS" and
                     r.get("applies_to") == "head" and r.get("source_sha") == recorded_head]
        if not snapshots:
            errors.append("accepted report lacks a current pr-state evidence snapshot")
        newest_pr_state = max((r for r in records if r.get("kind") == "pr-state"),
                              key=lambda r: r.get("captured_at", ""), default=None)
        if newest_pr_state not in snapshots:
            errors.append("newest pr-state snapshot is not current and PASS")
        for snapshot in ([newest_pr_state] if newest_pr_state in snapshots else []):
            try:
                captured = datetime.fromisoformat(snapshot["captured_at"].replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - captured.astimezone(timezone.utc)).total_seconds() > 300:
                    errors.append("pr-state snapshot is older than five minutes")
            except (KeyError, ValueError): errors.append("pr-state snapshot timestamp is invalid")
            try:
                payload = json.loads(Path(snapshot["path"]).read_text())
            except (OSError, json.JSONDecodeError) as error:
                errors.append("invalid pr-state payload: " + str(error)); continue
            if payload.get("headRefOid", "").lower() != recorded_head:
                errors.append("pr-state headRefOid differs from current head")
            checks = payload.get("statusCheckRollup")
            if not isinstance(checks, list) or any(
                    (check.get("conclusion") or check.get("state")) not in {"SUCCESS", "SKIPPED", "NEUTRAL"}
                    for check in checks):
                errors.append("pr-state required checks are missing, pending, or failing")
            if payload.get("reviewDecision") not in {"APPROVED", ""}:
                errors.append("pr-state review decision is not acceptable")
            if payload.get("reviewThreadsComplete") is not True:
                errors.append("pr-state does not prove complete review-thread closure")
            if payload.get("nameWithOwner", "").lower() != meta.get("repository", "").lower():
                errors.append("pr-state repository differs from artifact.repository")
            if payload.get("state") != "OPEN": errors.append("accepted report PR is not OPEN")
            declared_pr = meta.get("pr", "")
            if declared_pr not in {str(payload.get("number")), payload.get("url", "")}:
                errors.append("pr-state identity differs from artifact.pr")
            base_sha = meta.get("base", "").split("@")[-1].strip().lower()
            if payload.get("baseRefOid", "").lower() != base_sha:
                errors.append("pr-state base OID differs from artifact.base")
            policy = payload.get("requiredPolicy")
            if not isinstance(policy, dict) or not isinstance(policy.get("requiredChecks"), list) or not isinstance(policy.get("requiredApprovals"), int) or not policy.get("source"):
                errors.append("pr-state lacks authoritative required-check/approval policy")
            else:
                observed = {str(check.get("name") or check.get("context")): check.get("conclusion") or check.get("state") for check in checks}
                if any(observed.get(name) not in {"SUCCESS", "SKIPPED", "NEUTRAL"} for name in policy["requiredChecks"]):
                    errors.append("not every required check is represented and successful")
                approvals = sum(1 for review in payload.get("latestReviews", []) if review.get("state") == "APPROVED")
                if approvals < policy["requiredApprovals"]:
                    errors.append("required approval denominator is not satisfied")
        if meta.get("provenance-status") != "VERIFIED":
            errors.append("accepted report provenance is not VERIFIED")
        if 'data-public-audit="PASS"' not in source:
            errors.append("accepted report public-summary audit is not PASS")
        public = re.search(r'<details id="public-summary"([^>]*)>', source)
        attrs = public.group(1) if public else ""
        for name in ("auditor", "audited-at", "audit-denominator", "audit-evidence"):
            if not re.search(r'data-public-' + name + r'="[^"]+"', attrs):
                errors.append("accepted public-summary audit lacks " + name)
        audit_evidence = re.search(r'data-public-audit-evidence="(E-\d{3,})"', attrs)
        audit_record = next((r for r in records if audit_evidence and r.get("id") == audit_evidence.group(1)), None)
        auditor = re.search(r'data-public-auditor="([^"]+)"', attrs)
        denominator = re.search(r'data-public-audit-denominator="([^"]+)"', attrs)
        summary_digest = re.search(r'data-public-summary-digest="([0-9a-f]{64})"', attrs)
        public_block = re.search(r'<details id="public-summary".*?</details>', source, re.S)
        canonical_public = re.sub(r'data-public-(?:summary-digest|audit-revision)="[^"]*"',
                                  lambda m: m.group(0).split('=')[0] + '="AUDITED"', public_block.group(0)) if public_block else ""
        actual_public_digest = hashlib.sha256(canonical_public.encode()).hexdigest()
        if (not audit_record or audit_record.get("kind") != "public-audit" or
                audit_record.get("state") != "PASS" or audit_record.get("source_sha") != recorded_head or
                "human" not in audit_record.get("producer", "").lower() or
                not auditor or auditor.group(1).lower() not in audit_record.get("producer", "").lower() or
                not denominator or denominator.group(1).lower() not in audit_record.get("command", "").lower() or
                not summary_digest or summary_digest.group(1) != actual_public_digest or
                actual_public_digest not in audit_record.get("command", "") or
                not audit_record.get("captured_at")):
            errors.append("accepted public-summary audit evidence is not in manifest")
        evidence_by_id = {str(record.get("id")): record for record in records}
        proof = re.search(r'<details id="proof"([^>]*)>', source)
        if not proof or 'data-state="PASS"' not in proof.group(1) or f'data-source-sha="{recorded_head}"' not in proof.group(1):
            errors.append("decisive proof is not PASS on current head")
        for tag in re.findall(r'<[^>]*data-state="PASS"[^>]*data-ref-ids="[^"]+"[^>]*>|<[^>]*data-ref-ids="[^"]+"[^>]*data-state="PASS"[^>]*>', source):
            row_sha = re.search(r'data-source-sha="([0-9a-f]{40})"', tag, re.I)
            refs = re.search(r'data-ref-ids="([^"]+)"', tag).group(1).split()
            for ref in refs:
                if ref.startswith("E-"):
                    record = evidence_by_id.get(ref)
                    if not record or record.get("state") != "PASS" or (record.get("applies_to") == "head" and (not row_sha or record.get("source_sha") != row_sha.group(1).lower())):
                        errors.append("PASS row references non-current/non-PASS evidence " + ref)
        if (sealed in ("", "UNSEALED") or manifest_sealed in ("", "UNSEALED")) and not args.allow_unsealed:
            errors.append("accepted report is not sealed and current")
    if errors:
        for error in errors:
            print("ERROR", error)
        return 1
    print("PASS", rel, "schema=" + meta.get("schema-version", "?"),
          "revision=" + meta.get("revision", "?"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
