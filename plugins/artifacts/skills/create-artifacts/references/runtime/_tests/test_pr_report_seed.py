import importlib.util
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr_report_seed", ROOT / "scripts" / "seed-pr-report.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrReportSeedTests(unittest.TestCase):
    def test_set_record_evidence_replaces_the_structured_reference(self):
        source = (
            '<tr data-record-id="REV-001" data-ref-ids="E-001">'
            '<td>Review</td></tr>'
        )

        updated = MODULE.set_record_evidence(source, "REV-001", "E-002")

        self.assertIn('data-ref-ids="E-002"', updated)
        self.assertNotIn('data-ref-ids="E-001"', updated)

    def test_set_record_evidence_fails_if_the_record_is_missing(self):
        with self.assertRaisesRegex(ValueError, "missing data-ref-ids"):
            MODULE.set_record_evidence("<main></main>", "REV-001", "E-002")

    def test_set_section_evidence_sets_state_reason_and_refs(self):
        source = '<details id="sessions" class="issue"><summary>Sessions</summary></details>'
        updated = MODULE.set_section_evidence(source, "sessions", "E-003", "PASS")
        self.assertIn('data-state="PASS"', updated)
        self.assertIn('data-ref-ids="E-003"', updated)

    def test_session_rows_use_complete_analysis_receipt(self):
        evidence = {"sessions": [{
            "tool": "codex", "session_id": "abc", "classification": "primary",
            "sources": ["cortex", "local"], "analysis": {
                "path": "/tmp/abc.jsonl", "records_scanned": 9, "matched_excerpts": [{}, {}],
                "source_sha256": "a" * 64, "full_scan": True,
            },
        }]}
        rendered = MODULE.session_rows({"local_transcripts": [], "cortex_sessions": []}, evidence)
        self.assertIn("9 records fully scanned", rendered)
        self.assertIn("Primary PR lifecycle evidence", rendered)
        self.assertIn("cortex, local", rendered)

    def test_reseed_refreshes_scope(self):
        source = (
            '<div class="scope">old scope<code>abc</code></div>'
            '<details id="sessions" class="issue"><table class="ledger">'
            '<caption>old caption</caption><tr><th>Agent / human</th></tr>'
            '<tr><td>old</td></tr></table><div class="limit">old boundary</div></details>'
        )
        scope = "new scope"
        updated = re.sub(
            r'(<div class="scope">).*?(<code>)',
            lambda match: match.group(1) + MODULE.esc(scope) + match.group(2),
            source,
            count=1,
            flags=re.S,
        )
        self.assertIn('<div class="scope">new scope<code>', updated)

    def test_reseed_marks_existing_digests_unsealed(self):
        source = (
            '<meta name="artifact.report-digest" content="abc">'
            '<meta name="artifact.evidence-manifest-digest" content="def">'
        )
        updated = MODULE.unseal_report(source)
        self.assertEqual(updated.count('content="UNSEALED"'), 2)


if __name__ == "__main__":
    unittest.main()
