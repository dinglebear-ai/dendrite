"""Offline contract tests for the fixed LM Studio session bake-off."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "lmstudio-session-bakeoff.py"
CALLBACK = ROOT / "scripts" / "lmstudio-session-bakeoff.cjs"
CORPUS = ROOT / "research" / "session-bakeoff-corpus-v1.json"
LOG = Path("/Users/jmagar/docs/sessions/2026-08-29-axon-palette-aurora-polish.md")
EXPECTED_CORPUS_SHA = "8e5c2f9bfbf1fea16f45dc935102e9c9bd6867e9ce53561b2d4602335a8cd017"
EXPECTED_SOURCE_SHA = "9755104caa34833d76c509846821e0f0bdb06e9cb5ae53b7b4f4c92ec5305a90"
EXPECTED_LOG_SHA = "28887f13dd8cd52f9a118561975e6c2d8ea9b83f5b29c55ff96c006c80461e9b"
NODE = subprocess.check_output(["node", "-p", "process.execPath"], text=True).strip()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha_value(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_bytes(value) + b"\n")


def load_corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def run_tool(*args: object, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(TOOL), *map(str, args)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def all_primary_selectors(corpus: dict) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for packet in corpus["packets"]:
        for selector in packet["primary_units"]:
            key = (selector["record_id"], selector["turn_id"])
            if key not in seen:
                seen.add(key)
                result.append(key)
    return result


def mirror_key(record_id: int) -> str:
    if record_id in {28, 42}:
        return "unit-mirror-start-state"
    if record_id in {3699, 3701}:
        return "unit-mirror-live-dom-fix"
    if record_id in {3753, 3755, 3761}:
        return "unit-mirror-build-install"
    return f"unit-record-{record_id}"


def create_fake_validator(directory: Path) -> Path:
    validator = directory / "fake-session-deep-dive.py"
    validator.write_text(
        """#!/usr/bin/env python3
import hashlib, json, pathlib, sys
if len(sys.argv) != 4 or sys.argv[1] != 'verify-prepared' or sys.argv[2] != '--work-dir':
    raise SystemExit(2)
w = pathlib.Path(sys.argv[3])
h = lambda name: hashlib.sha256((w / name).read_bytes()).hexdigest()
m = json.loads((w / 'manifest.json').read_text())
print(json.dumps({
  'schema_version': 1,
  'validation_contract': 'session-deep-dive-prepared-validation-v1',
  'validated': True,
  'source_sha256': m['source']['sha256'],
  'manifest_sha256': h('manifest.json'),
  'prepare_seal_sha256': h('prepare-seal.json'),
  'media_ledger_sha256': h('media-ledger.json'),
  'unit_index_sha256': h('unit-index.json'),
  'record_index_sha256': h('record-index.json'),
  'prepared_contract': m['prepared_contract'],
  'redaction_contract': m['redaction_contract'],
}, sort_keys=True, separators=(',', ':')))
""",
        encoding="utf-8",
    )
    validator.chmod(validator.stat().st_mode | stat.S_IXUSR)
    return validator


def create_prepared_v4(directory: Path, corpus: dict) -> tuple[Path, Path]:
    workdir = directory / "prepared-v4"
    workdir.mkdir()
    selectors = all_primary_selectors(corpus)
    grouped: dict[str, list[tuple[int, str]]] = {}
    for record_id, turn_id in selectors:
        grouped.setdefault(mirror_key(record_id), []).append((record_id, turn_id))
    units = []
    record_rows = []
    for unit_id, members in grouped.items():
        semantic_kind = "state_observation"
        text = "Prepared redacted evidence for record selectors " + ", ".join(
            str(record_id) for record_id, _ in members
        )
        units.append(
            {
                "normalized_unit_id": unit_id,
                "source_selectors": [
                    {"record_id": record_id, "turn_id": turn_id}
                    for record_id, turn_id in members
                ],
                "semantic_kind": semantic_kind,
                "text": text,
                "content_sha256": sha_value(
                    {"semantic_kind": semantic_kind, "text": text}
                ),
            }
        )
        for record_id, turn_id in members:
            record_rows.append(
                {
                    "record_id": record_id,
                    "turn_id": turn_id,
                    "normalized_unit_ids": [unit_id],
                }
            )
    record_index = {
        "schema_version": 4,
        "kind": "session-deep-dive-record-index-v4",
        "source_sha256": EXPECTED_SOURCE_SHA,
        "records": sorted(record_rows, key=lambda row: row["record_id"]),
    }
    unit_index = {
        "schema_version": 4,
        "kind": "session-deep-dive-unit-index-v4",
        "source_sha256": EXPECTED_SOURCE_SHA,
        "units": units,
    }
    write_json(workdir / "record-index.json", record_index)
    write_json(workdir / "unit-index.json", unit_index)

    visual_by_key: dict[tuple[int, str], dict] = {}
    for packet in corpus["packets"]:
        for selector in packet["primary_units"]:
            if selector.get("visual_group"):
                visual_by_key[(selector["record_id"], selector["turn_id"])] = selector
    occurrences = []
    assets = []
    groups = []
    for selector in visual_by_key.values():
        count = 2 if selector.get("multi_image") else 1
        occurrence_ids = []
        asset_hashes = []
        for ordinal in range(1, count + 1):
            digest = hashlib.sha256(
                f"{selector['visual_group']}:{ordinal}".encode()
            ).hexdigest()
            occurrence_id = f"occ-{selector['record_id']}-{ordinal}"
            occurrence_ids.append(occurrence_id)
            asset_hashes.append(digest)
            assets.append(
                {
                    "asset_sha256": digest,
                    "media_type": "image/png",
                    "width": 640,
                    "height": 480,
                    "byte_length": 4096 + ordinal,
                }
            )
            occurrences.append(
                {
                    "occurrence_id": occurrence_id,
                    "record_id": selector["record_id"],
                    "turn_id": selector["turn_id"],
                    "ordinal": ordinal,
                    "asset_sha256": digest,
                    "visual_group": selector["visual_group"],
                }
            )
        groups.append(
            {
                "visual_group": selector["visual_group"],
                "occurrence_ids": occurrence_ids,
                "asset_sha256s": sorted(set(asset_hashes)),
            }
        )
    media = {
        "schema_version": 1,
        "contract": "session-deep-dive-media-ledger-v1",
        "source_sha256": EXPECTED_SOURCE_SHA,
        "occurrences": occurrences,
        "assets": assets,
        "groups": groups,
    }
    write_json(workdir / "media-ledger.json", media)
    reseal_prepared(workdir, corpus, initial=True)
    return workdir, create_fake_validator(directory)


def reseal_prepared(workdir: Path, corpus: dict, *, initial: bool = False) -> None:
    manifest = {
        "schema_version": 4,
        "prepared_contract": "session-deep-dive-prepared-v4",
        "redaction_contract": "session-deep-dive-redaction-v6",
        "session_id": corpus["session_id"],
        "source": {"sha256": EXPECTED_SOURCE_SHA, "bytes": 157155006},
        "record_index_sha256": sha_file(workdir / "record-index.json"),
        "unit_index_sha256": sha_file(workdir / "unit-index.json"),
        "media_ledger_sha256": sha_file(workdir / "media-ledger.json"),
    }
    write_json(workdir / "manifest.json", manifest)
    seal = {
        "schema_version": 4,
        "kind": "session-deep-dive-prepare-seal-v4",
        "prepared_contract": "session-deep-dive-prepared-v4",
        "redaction_contract": "session-deep-dive-redaction-v6",
        "source_sha256": EXPECTED_SOURCE_SHA,
        "manifest_sha256": sha_file(workdir / "manifest.json"),
        "record_index_sha256": sha_file(workdir / "record-index.json"),
        "unit_index_sha256": sha_file(workdir / "unit-index.json"),
        "media_ledger_sha256": sha_file(workdir / "media-ledger.json"),
    }
    write_json(workdir / "prepare-seal.json", seal)


def build_bundle(directory: Path, corpus: dict) -> tuple[dict, Path, Path, Path]:
    workdir, validator = create_prepared_v4(directory, corpus)
    output = directory / "bundle.json"
    completed = run_tool(
        "build",
        "--corpus",
        CORPUS,
        "--prepared-workdir",
        workdir,
        "--corroborating-log",
        LOG,
        "--validator",
        validator,
        "--output",
        output,
    )
    if completed.returncode:
        raise AssertionError(f"build failed: {completed.stderr}\n{completed.stdout}")
    return json.loads(output.read_text()), output, workdir, validator


def support_set(unit: dict) -> set[int | str]:
    if unit["source_class"] == "primary_transcript":
        return {row["record_id"] for row in unit["source_selectors"]}
    return {unit["log_id"]}


def complete_response(bundle: dict, corpus: dict, *, rotation: int = 0) -> dict:
    packets = bundle["packets"][rotation:] + bundle["packets"][:rotation]
    facts_by_packet: dict[str, list[dict]] = {}
    for fact in corpus["gold_facts"]:
        facts_by_packet.setdefault(fact["packet_id"], []).append(fact)
    packet_results = []
    all_claims = []
    for packet in packets:
        claims = []
        for fact in facts_by_packet.get(packet["packet_id"], []):
            citations = []
            for group in fact["support_groups"]:
                citation = next(
                    unit["input_id"]
                    for unit in packet["input_units"]
                    if support_set(unit).intersection(group)
                )
                if citation not in citations:
                    citations.append(citation)
            claim = {
                "claim_id": fact["fact_id"],
                "predicate_id": fact["fact_id"],
                "polarity": "affirmed",
                "state": fact["allowed_states"][0],
                "text": fact["example_text"],
                "citations": citations,
            }
            claims.append(claim)
            all_claims.append(claim["claim_id"])
        packet_results.append(
            {
                "packet_id": packet["packet_id"],
                "claims": claims,
                "unit_dispositions": [
                    {"input_id": unit["input_id"], "disposition": "used"}
                    for unit in packet["input_units"]
                ],
            }
        )
    return {
        "schema_version": 2,
        "kind": "session_bakeoff_response",
        "corpus_sha256": bundle["corpus_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
        "packet_results": packet_results,
        "report_outline": [
            {
                "section_id": "evidence",
                "title": "Status and evidence",
                "purpose": "Preserve state boundaries and unresolved work.",
                "claim_ids": all_claims,
            }
        ],
    }


def blinded_review(bundle: dict, responses: list[dict], points: int = 5) -> dict:
    return {
        "schema_version": 1,
        "kind": "session_bakeoff_blinded_review",
        "corpus_sha256": bundle["corpus_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
        "response_sha256s": [sha_value(response) for response in responses],
        "candidate_label": "candidate-012345abcdef",
        "reviews": [
            {
                "reviewer_label": "reviewer-fedcba543210",
                "run_scores": [
                    {
                        "blind_label": f"run-{index:03d}",
                        "dimensions": [
                            {"dimension": row["dimension"], "points": points}
                            for row in bundle["corpus_manifest"]["blinded_review_rubric"]
                        ],
                    }
                    for index in range(1, 4)
                ],
            }
        ],
    }


def score(
    directory: Path, bundle_path: Path, bundle: dict, responses: list[dict], review: dict
) -> subprocess.CompletedProcess[str]:
    response_paths = []
    for index, response in enumerate(responses, 1):
        path = directory / f"response-{index}.json"
        write_json(path, response)
        response_paths.extend(["--response", path])
    review_path = directory / "review.json"
    write_json(review_path, review)
    return run_tool(
        "score",
        "--corpus",
        CORPUS,
        "--bundle",
        bundle_path,
        *response_paths,
        "--blinded-review",
        review_path,
        "--output",
        directory / "score.json",
    )


class ManifestContractTests(unittest.TestCase):
    def test_corpus_is_compiled_not_self_resealable_and_support_is_complete(self) -> None:
        corpus = load_corpus()
        result = run_tool("validate-manifest", "--corpus", CORPUS)
        self.assertEqual(result.returncode, 0, result.stderr)
        unsigned = dict(corpus)
        unsigned.pop("manifest_sha256")
        self.assertEqual(sha_value(unsigned), EXPECTED_CORPUS_SHA)
        self.assertEqual(corpus["manifest_sha256"], EXPECTED_CORPUS_SHA)
        self.assertEqual(sum(row["weight"] for row in corpus["gold_facts"]), 54)
        self.assertEqual(corpus["gold_facts"][1]["support_groups"], [[3772], [3778, 3783, 3791], [4986]])
        self.assertFalse(
            any(3900 in group for group in corpus["gold_facts"][1]["support_groups"])
        )
        self.assertEqual(corpus["execution_contract"]["required_repeats"], 3)
        self.assertEqual(corpus["scoring_contract"]["median_hard_weight"], 0.5)

        with tempfile.TemporaryDirectory() as temporary:
            forged = json.loads(json.dumps(corpus))
            forged["gold_facts"][0]["example_text"] = "forged"
            unsigned = dict(forged)
            unsigned.pop("manifest_sha256")
            forged["manifest_sha256"] = sha_value(unsigned)
            path = Path(temporary) / "forged.json"
            write_json(path, forged)
            rejected = run_tool("validate-manifest", "--corpus", path)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("resealing is forbidden", rejected.stderr)


class PreparedV4BuilderTests(unittest.TestCase):
    def test_builder_reconstructs_every_selector_deduplicates_mirrors_and_is_deterministic(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle, first_path, workdir, validator = build_bundle(directory, corpus)
            second_path = directory / "bundle-two.json"
            result = run_tool(
                "build", "--corpus", CORPUS,
                "--prepared-workdir", workdir,
                "--corroborating-log", LOG,
                "--validator", validator,
                "--output", second_path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertEqual(bundle["prepared_binding"]["source_sha256"], EXPECTED_SOURCE_SHA)
            self.assertEqual(bundle["prepared_binding"]["corroborating_log_sha256"], EXPECTED_LOG_SHA)
            packet_a = bundle["packets"][0]
            self.assertEqual(len(packet_a["selection_receipts"]), 16)
            self.assertEqual(len(packet_a["input_units"]), 15)
            packet_b2 = next(row for row in bundle["packets"] if row["packet_id"] == "B2")
            self.assertLess(len(packet_b2["input_units"]), len(packet_b2["selection_receipts"]))
            self.assertTrue(all(len(row["input_units"]) <= 24 for row in bundle["packets"]))
            all_receipts = [receipt for row in bundle["packets"] for receipt in row["selection_receipts"]]
            self.assertEqual(
                sum("record_id" in receipt for receipt in all_receipts),
                sum(len(row["primary_units"]) for row in corpus["packets"]),
            )
            self.assertFalse(any("raw_base64" in json.dumps(row) for row in bundle["packets"]))

    def test_python_preflight_rebuilds_bundle_and_fails_on_tamper(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle, bundle_path, workdir, validator = build_bundle(directory, corpus)
            result = run_tool(
                "preflight", "--corpus", CORPUS, "--bundle", bundle_path,
                "--prepared-workdir", workdir, "--corroborating-log", LOG,
                "--validator", validator,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt["validated"])
            self.assertEqual(receipt["bundle_sha256"], bundle["bundle_sha256"])
            tampered = json.loads(bundle_path.read_text())
            tampered["packets"][0]["title"] = "tampered"
            unsigned = dict(tampered)
            unsigned.pop("bundle_sha256")
            tampered["bundle_sha256"] = sha_value(unsigned)
            write_json(bundle_path, tampered)
            rejected = run_tool(
                "preflight", "--corpus", CORPUS, "--bundle", bundle_path,
                "--prepared-workdir", workdir, "--corroborating-log", LOG,
                "--validator", validator,
            )
            self.assertEqual(rejected.returncode, 2)

    def test_multi_image_flag_requires_two_distinct_ledger_assets(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            workdir, validator = create_prepared_v4(directory, corpus)
            media_path = workdir / "media-ledger.json"
            media = json.loads(media_path.read_text())
            group = next(row for row in media["groups"] if row["visual_group"] == "enter-regression-pair")
            removed_occurrence = group["occurrence_ids"].pop()
            media["occurrences"] = [row for row in media["occurrences"] if row["occurrence_id"] != removed_occurrence]
            remaining = next(row for row in media["occurrences"] if row["occurrence_id"] == group["occurrence_ids"][0])
            group["asset_sha256s"] = [remaining["asset_sha256"]]
            write_json(media_path, media)
            reseal_prepared(workdir, corpus)
            rejected = run_tool(
                "build", "--corpus", CORPUS, "--prepared-workdir", workdir,
                "--corroborating-log", LOG, "--validator", validator,
                "--output", directory / "bundle.json",
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("fewer than two distinct", rejected.stderr)

    def test_production_v3_or_missing_v4_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            validator = create_fake_validator(directory)
            rejected = run_tool(
                "build", "--corpus", CORPUS, "--prepared-workdir", directory,
                "--corroborating-log", LOG, "--validator", validator,
                "--output", directory / "bundle.json",
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("prepared manifest is missing", rejected.stderr)


class SafetyTests(unittest.TestCase):
    UNSAFE_TEXT = (
        "~/private/session.png",
        "/Users/example/secret.png",
        "/tmp/capture.png",
        r"C:\\Users\\example\\capture.png",
        r"\\\\server\\share\\capture.png",
        "../capture.png",
        "data:image/png;base64,AAAA",
        "blob:https://example.test/deadbeef",
        "A" * 160,
        "a_b-" * 40,
    )

    def mutate_first_unit(self, workdir: Path, corpus: dict, text: str, *, extra_key: str | None = None) -> None:
        path = workdir / "unit-index.json"
        index = json.loads(path.read_text())
        unit = index["units"][0]
        unit["text"] = text
        unit["content_sha256"] = sha_value({"semantic_kind": unit["semantic_kind"], "text": text})
        if extra_key:
            unit[extra_key] = "forbidden"
        write_json(path, index)
        reseal_prepared(workdir, corpus)

    def test_unsafe_payload_forms_fail_even_if_sidecars_and_fake_receipt_are_resealed(self) -> None:
        corpus = load_corpus()
        for unsafe in self.UNSAFE_TEXT:
            with self.subTest(unsafe=unsafe[:32]), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                workdir, validator = create_prepared_v4(directory, corpus)
                self.mutate_first_unit(workdir, corpus, unsafe)
                rejected = run_tool(
                    "build", "--corpus", CORPUS, "--prepared-workdir", workdir,
                    "--corroborating-log", LOG, "--validator", validator,
                    "--output", directory / "bundle.json",
                )
                self.assertEqual(rejected.returncode, 2, unsafe)

    def test_forged_raw_base64_and_source_path_keys_always_fail(self) -> None:
        corpus = load_corpus()
        for key in ("raw_base64", "source_path"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                workdir, validator = create_prepared_v4(directory, corpus)
                self.mutate_first_unit(workdir, corpus, "safe evidence", extra_key=key)
                rejected = run_tool(
                    "build", "--corpus", CORPUS, "--prepared-workdir", workdir,
                    "--corroborating-log", LOG, "--validator", validator,
                    "--output", directory / "bundle.json",
                )
                self.assertEqual(rejected.returncode, 2)

    def test_safe_repo_relative_path_and_https_documentation_url_are_preserved(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            workdir, validator = create_prepared_v4(directory, corpus)
            text = "See src/components/Terminal.tsx and https://developer.mozilla.org/docs/Web/API."
            self.mutate_first_unit(workdir, corpus, text)
            output = directory / "bundle.json"
            result = run_tool(
                "build", "--corpus", CORPUS, "--prepared-workdir", workdir,
                "--corroborating-log", LOG, "--validator", validator,
                "--output", output,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(text, output.read_text())


class ScoringTests(unittest.TestCase):
    def test_all_three_runs_and_blinded_review_are_mandatory(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle, bundle_path, _, _ = build_bundle(directory, corpus)
            response = complete_response(bundle, corpus)
            review = blinded_review(bundle, [response, response, response])
            rejected = score(directory, bundle_path, bundle, [response, response], review)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("one three-repeat callback or exactly three", rejected.stderr)

    def test_exact_composite_uses_median_worst_blinded_and_consistency_without_cherry_pick(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle, bundle_path, _, _ = build_bundle(directory, corpus)
            responses = [complete_response(bundle, corpus) for _ in range(3)]
            # Make only run 2 miss ordinary G42. Median remains 100, but both
            # the worst-run term and weighted consistency must retain the miss.
            packet_c = next(row for row in responses[1]["packet_results"] if row["packet_id"] == "C")
            packet_c["claims"] = [row for row in packet_c["claims"] if row["predicate_id"] != "G42"]
            responses[1]["report_outline"][0]["claim_ids"].remove("G42")
            review = blinded_review(bundle, responses, points=4)
            completed = score(directory, bundle_path, bundle, responses, review)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((directory / "score.json").read_text())
            hard_worst = round(100 * 53 / 54, 6)
            qualitative = round(100 * 36 / 45, 6)
            consistency = hard_worst
            expected = round(0.5 * 100 + 0.2 * hard_worst + 0.2 * qualitative + 0.1 * consistency, 6)
            self.assertEqual(result["aggregate"]["hard_scores"], [100.0, hard_worst, 100.0])
            self.assertEqual(result["aggregate"]["repeat_consistency_score"], consistency)
            self.assertEqual(result["aggregate"]["final_composite_score"], expected)
            self.assertEqual(result["aggregate"]["repeat_count"], 3)

    def test_multi_component_gold_requires_every_support_group(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle, bundle_path, _, _ = build_bundle(directory, corpus)
            responses = [complete_response(bundle, corpus) for _ in range(3)]
            claim = next(
                claim
                for row in responses[0]["packet_results"]
                for claim in row["claims"]
                if claim["predicate_id"] == "G02"
            )
            lookup = {unit["input_id"]: unit for packet in bundle["packets"] for unit in packet["input_units"]}
            claim["citations"] = [
                citation for citation in claim["citations"]
                if 4986 not in support_set(lookup[citation])
            ]
            review = blinded_review(bundle, responses)
            completed = score(directory, bundle_path, bundle, responses, review)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((directory / "score.json").read_text())
            self.assertIn("G02", result["runs"][0]["gold"]["missing_fact_ids"])
            self.assertEqual(result["runs"][0]["hard_score"], round(100 * 52 / 54, 6))

    def test_structured_negation_is_safe_but_false_affirmation_auto_fails(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle, bundle_path, _, _ = build_bundle(directory, corpus)
            responses = [complete_response(bundle, corpus) for _ in range(3)]
            packet_f = next(row for row in responses[0]["packet_results"] if row["packet_id"] == "F")
            citation = packet_f["unit_dispositions"][0]["input_id"]
            negative = {
                "claim_id": "honest-clean-negative",
                "predicate_id": "C09",
                "polarity": "negated",
                "state": "observed",
                "text": "The worktree was not clean.",
                "citations": [citation],
            }
            packet_f["claims"].append(negative)
            responses[0]["report_outline"][0]["claim_ids"].append(negative["claim_id"])
            review = blinded_review(bundle, responses)
            completed = score(directory, bundle_path, bundle, responses, review)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((directory / "score.json").read_text())
            self.assertFalse(result["runs"][0]["auto_failure"])

            negative["polarity"] = "affirmed"
            negative["text"] = "The worktree was clean."
            review = blinded_review(bundle, responses)
            completed = score(directory, bundle_path, bundle, responses, review)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((directory / "score.json").read_text())
            self.assertTrue(result["runs"][0]["auto_failure"])
            self.assertIn("C09", result["runs"][0]["failure_reasons"])
            self.assertEqual(result["runs"][0]["hard_score"], 0.0)

    def test_blinding_contract_rejects_model_or_reviewer_identity_fields(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle, bundle_path, _, _ = build_bundle(directory, corpus)
            responses = [complete_response(bundle, corpus) for _ in range(3)]
            review = blinded_review(bundle, responses)
            review["model_name"] = "qwen"
            rejected = score(directory, bundle_path, bundle, responses, review)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("unsupported fields", rejected.stderr)


class CallbackStaticTests(unittest.TestCase):
    def test_one_loaded_model_transaction_runs_one_vision_call_and_three_by_eight_packets(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, bundle_path, _, _ = build_bundle(directory, corpus)
            script = r"""
const fs = require('node:fs');
const h = require(process.argv[1]);
const bundle = h.validateBundle(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
const info = {
  modelKey: 'model-key', identifier: 'identifier', indexedModelIdentifier: 'indexed',
  selectedVariant: 'variant', instanceReference: 'instance', deviceIdentifier: null,
  contextLength: 32768, ttlMs: null, lastUsedTime: null,
};
const config = {contextLength: 32768, temperature: 0};
const state = {status: 'idle', queued: 0};
const snapshot = h.normalizeSnapshot(info, config, state);
const environment = {
  modelKey: info.modelKey, identifier: info.identifier,
  indexedModelIdentifier: info.indexedModelIdentifier, selectedVariant: info.selectedVariant,
  instanceReference: info.instanceReference, contextLength: info.contextLength,
  loadConfigSha256: h.sha256Value(snapshot.load_config), snapshotSha256: h.sha256Value(snapshot),
};
let respondCalls = 0;
const model = {
  vision: true,
  async getModelInfo() { return info; },
  async getLoadConfig() { return config; },
  async getInstanceProcessingState() { return state; },
  async applyPromptTemplate() { return 'formatted'; },
  async countTokens() { return 10; },
  async respond(_chat, options) {
    respondCalls += 1;
    const schema = options.structured.jsonSchema;
    if (schema.properties.status_text) {
      return {content: JSON.stringify(h.syntheticVisionGold()), stats: {stopReason: 'eosFound'}};
    }
    const packetId = schema.properties.packet_result.properties.packet_id.const;
    const inputIds = schema.properties.packet_result.properties.unit_dispositions.items.properties.input_id.enum;
    return {
      content: JSON.stringify({
        schema_version: 2, kind: 'session_bakeoff_packet_response',
        corpus_sha256: bundle.corpus_sha256, bundle_sha256: bundle.bundle_sha256,
        packet_result: {
          packet_id: packetId, claims: [],
          unit_dispositions: inputIds.map(input_id => ({input_id, disposition: 'used'})),
        },
        report_sections: [{
          section_id: `section-${packetId}`, title: `Packet ${packetId}`,
          purpose: 'Bounded packet evidence.', claim_ids: [],
        }],
      }),
      stats: {stopReason: 'eosFound'},
    };
  },
};
let listLoadedCalls = 0;
const client = {
  llm: {async listLoaded() { listLoadedCalls += 1; return [model]; }},
  files: {async prepareImageBase64() { return {isImage() { return true; }}; }},
};
(async () => {
  const result = await h.runInferenceBatch(
    client, bundle, {deadlineMs: 1000000, maxTokens: 1024, reasoningBudget: 0, repeats: 3}, environment,
  );
  if (listLoadedCalls !== 1 || respondCalls !== 25 || result.repeatRuns.length !== 3) {
    throw new Error(JSON.stringify({listLoadedCalls, respondCalls, repeats: result.repeatRuns.length}));
  }
  const orders = result.repeatRuns.map(run => run.packet_order.join(','));
  if (new Set(orders).size !== 3) throw new Error('packet rotations are not distinct');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
            completed = subprocess.run(
                [NODE, "-e", script, str(CALLBACK), str(bundle_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_js_independently_reconstructs_all_prepared_selectors_and_media_bindings(self) -> None:
        corpus = load_corpus()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _bundle, bundle_path, workdir, _ = build_bundle(directory, corpus)
            script = r"""
const fs = require('node:fs');
const h = require(process.argv[1]);
const bundle = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
h.validateBundle(bundle);
h.verifyPreparedAgainstBundle({preparedWorkdir: process.argv[3], corroboratingLog: process.argv[4]}, bundle);
"""
            completed = subprocess.run(
                [NODE, "-e", script, str(CALLBACK), str(bundle_path), str(workdir), str(LOG)],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            media_path = workdir / "media-ledger.json"
            media = json.loads(media_path.read_text())
            media["groups"][0]["asset_sha256s"] = ["f" * 64]
            write_json(media_path, media)
            rejected = subprocess.run(
                [NODE, "-e", script, str(CALLBACK), str(bundle_path), str(workdir), str(LOG)],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_callback_has_no_arbitrary_sdk_entry_and_uses_list_loaded_only(self) -> None:
        source = CALLBACK.read_text(encoding="utf-8")
        self.assertNotIn("--sdk-entry", source)
        self.assertNotRegex(source, r"\.model\s*\(")
        self.assertNotRegex(source, r"\.load\s*\(")
        self.assertNotRegex(source, r"\.unload\s*\(")
        self.assertIn("listLoaded", source)
        for name in (
            "LMSTUDIO_BAKEOFF_SDK_ENTRY_PATH",
            "LMSTUDIO_BAKEOFF_SDK_ENTRY_SHA256",
            "LMSTUDIO_BAKEOFF_SDK_CLOSURE_SHA256",
            "LMSTUDIO_BAKEOFF_SDK_DEPENDENCY_CLOSURE_SHA256",
        ):
            self.assertIn(name, source)

    def test_callback_fails_closed_before_sdk_require_when_binding_is_absent(self) -> None:
        completed = subprocess.run(
            [NODE, str(CALLBACK)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": os.environ.get("PATH", "")},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("LMSTUDIO_BAKEOFF_SDK_ENTRY_PATH", completed.stderr)

    def test_js_safety_validator_rejects_forged_keys_and_unsafe_values_but_allows_safe_provenance(self) -> None:
        script = r"""
const h = require(process.argv[1]);
const bad = [
  {raw_base64: 'AAAA'}, {source_path: 'src/x'}, {text: '~/x'},
  {text: '/Users/a/x'}, {text: '/tmp/x'}, {text: 'C:\\x'},
  {text: '\\\\server\\share'}, {text: '../x'}, {text: 'data:image/png;base64,A'},
  {text: 'A'.repeat(160)}, {text: 'a_b-'.repeat(40)},
];
for (const value of bad) {
  let failed = false;
  try { h.assertSafe(value, 'test'); } catch (_) { failed = true; }
  if (!failed) throw new Error('unsafe value accepted: ' + JSON.stringify(value));
}
h.assertSafe({text: 'src/components/X.tsx https://developer.mozilla.org/docs'}, 'safe');
"""
        completed = subprocess.run(
            [NODE, "-e", script, str(CALLBACK)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
