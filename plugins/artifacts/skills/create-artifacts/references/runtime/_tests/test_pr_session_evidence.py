import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr_session_evidence", ROOT / "scripts" / "build-pr-session-evidence.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrSessionEvidenceTests(unittest.TestCase):
    def test_combines_cortex_and_local_identity_and_prioritizes_primary(self):
        context = {
            "local_transcripts": [{
                "tool": "codex", "session_id": "primary", "path": "/tmp/a",
                "score": 4, "is_subagent_transcript": False,
            }],
            "cortex_sessions": [{
                "tool": "codex", "session_id": "primary", "queries": ["branch"],
                "session_key": "key",
            }],
        }
        result = MODULE.combine_candidates(context, {"primary"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sources"], ["cortex", "local"])
        self.assertEqual(result[0]["classification"], "primary")

    def test_complete_scan_redacts_secrets_and_omits_tool_arguments(self):
        with tempfile.TemporaryDirectory() as raw:
            transcript = Path(raw) / "session.jsonl"
            records = [
                {"timestamp": "2026-01-01T00:00:00Z", "type": "response_item", "payload": {
                    "type": "message", "role": "assistant", "content": [{
                        "type": "output_text", "text": "Implemented unassigned device work token=supersecretvalue"
                    }]}},
                {"timestamp": "2026-01-01T00:00:01Z", "type": "response_item", "payload": {
                    "type": "function_call", "name": "exec_command", "arguments": "password=do-not-copy"
                }},
            ]
            transcript.write_text("".join(json.dumps(item) + "\n" for item in records))
            result = MODULE.scan_transcript(transcript, ["unassigned device"], 10, 200)
            self.assertTrue(result["full_scan"])
            self.assertEqual(result["snapshot_bytes"], transcript.stat().st_size)
            self.assertFalse(result["source_grew_during_capture"])
            self.assertEqual(result["records_scanned"], 2)
            self.assertEqual(result["tool_calls"], {"exec_command": 1})
            rendered = json.dumps(result)
            self.assertNotIn("supersecretvalue", rendered)
            self.assertNotIn("do-not-copy", rendered)
            self.assertIn("[REDACTED]", rendered)


if __name__ == "__main__":
    unittest.main()
