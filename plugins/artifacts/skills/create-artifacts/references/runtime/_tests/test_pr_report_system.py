import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from _app.pr_report_system import build_manifest, load_registry, scan_public, semantic_diff

ROOT = Path(__file__).resolve().parent.parent


class PrReportSystemTest(unittest.TestCase):
    def test_registry_is_the_exact_six_stage_twenty_nine_section_denominator(self):
        registry = load_registry()
        self.assertEqual(len(registry["stages"]), 6)
        self.assertEqual(sum(len(stage["sections"]) for stage in registry["stages"]), 29)

    def test_template_builds_machine_manifest_and_claim_evidence_graph(self):
        manifest = build_manifest(ROOT / "pr-reports/_template.html")
        self.assertEqual(manifest["manifest_schema"], 1)
        self.assertEqual(sum(len(stage["sections"]) for stage in manifest["stages"]), 29)
        self.assertIn("dangling_references", manifest["graph_issues"])
        self.assertEqual(manifest["readiness"]["sections"]["total"], 29)

    def test_public_scanner_fails_closed_on_private_values(self):
        findings = scan_public("/Users/alice/private token=secret 192.168.1.10")
        self.assertGreaterEqual(len(findings), 3)

    def test_semantic_diff_reports_field_level_changes(self):
        result = semantic_diff({"sections":{"a":{"state":"PASS"}}},
                               {"sections":{"a":{"state":"STALE"},"b":{"state":"PASS"}}})
        self.assertIn("a", result["sections"]["changed"])
        self.assertIn("b", result["sections"]["added"])

    def test_cli_compiles_manifest_and_records_digest_bound_acknowledgement(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.html"
            report.write_text((ROOT / "pr-reports/_template.html").read_text())
            subprocess.run(["python3", str(ROOT / "scripts/pr-report.py"), "compile", str(report)], check=True, capture_output=True)
            self.assertIn('id="pr-report-manifest"', report.read_text())
            first = report.read_bytes()
            subprocess.run(["python3", str(ROOT / "scripts/pr-report.py"), "compile", str(report)], check=True, capture_output=True)
            self.assertEqual(first, report.read_bytes())
            subprocess.run(["python3", str(ROOT / "scripts/pr-report.py"), "acknowledge", str(report), "problem", "--reviewer", "reviewer@example"], check=True, capture_output=True)
            record = json.loads(report.with_suffix(".review.jsonl").read_text())
            self.assertEqual(record["checkpoint"], "problem")


if __name__ == "__main__":
    unittest.main()
