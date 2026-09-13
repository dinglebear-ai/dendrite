import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr_context_discovery", ROOT / "scripts" / "discover-pr-context.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrContextDiscoveryTests(unittest.TestCase):
    def test_pr_context_fetches_every_file_and_commit_page(self):
        pr = {
            "html_url": "https://github.com/example/core/pull/13",
            "title": "Large pull request",
            "body": "",
            "state": "open",
            "draft": True,
            "created_at": "2026-09-01T00:00:00Z",
            "updated_at": "2026-09-02T00:00:00Z",
            "base": {"ref": "main", "sha": "b" * 40},
            "head": {"ref": "feature", "sha": "h" * 40},
        }
        files = [{"filename": f"lib/file_{index:03d}.ex"} for index in range(143)]
        commits = [
            {"sha": f"{index:040x}", "commit": {"message": f"Commit {index}"}}
            for index in range(101)
        ]

        def fake_gh(path):
            if path == "repos/example/core/pulls/13":
                return pr
            if path.startswith("repos/example/core/pulls/13/files?"):
                page = int(path.rsplit("page=", 1)[1])
                return files[(page - 1) * 100:page * 100]
            if path.startswith("repos/example/core/pulls/13/commits?"):
                page = int(path.rsplit("page=", 1)[1])
                return commits[(page - 1) * 100:page * 100]
            if path.startswith("repos/example/core/compare/"):
                return {"merge_base_commit": {"sha": "m" * 40}}
            self.fail(f"unexpected GitHub path: {path}")

        with patch.object(MODULE, "gh", side_effect=fake_gh):
            context = MODULE.pr_context("example/core", 13)

        self.assertEqual(context["files"], [item["filename"] for item in files])
        self.assertEqual(len(context["commits"]), 101)
        self.assertEqual(context["commits"][-1]["message"], "Commit 100")

    def test_artifact_matching_explains_exact_branch_and_changed_path(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for folder in MODULE.ARTIFACT_DIRS:
                (root / folder).mkdir()
            artifact = root / "sessions" / "trial.html"
            artifact.write_text("fix/hidden-red-integration-tests test/example_test.exs")
            pr = {
                "title": "Fix hidden test", "head_branch": "fix/hidden-red-integration-tests",
                "head_sha": "a" * 40, "url": "https://github.com/example/core/pull/13",
                "number": 13, "files": ["test/example_test.exs"],
            }
            match = MODULE.match_artifacts(root, pr)[0]
            self.assertEqual(match["path"], str(artifact.resolve()))
            self.assertIn("exact-branch", {item["kind"] for item in match["signals"]})
            self.assertIn("changed-path", {item["kind"] for item in match["signals"]})

    def test_local_transcript_rejects_bare_pr_number_collision(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "unrelated.jsonl").write_text('{"message":"pull/13"}\n')
            pr = {
                "head_branch": "fix/hidden-red", "head_sha": "a" * 40,
                "url": "https://github.com/example/core/pull/13", "number": 13,
            }
            self.assertEqual(MODULE.local_transcripts(pr, [root]), [])

    def test_cortex_discovery_reports_when_it_was_not_attempted(self):
        pr = {
            "head_branch": "feature", "head_sha": "a" * 40,
            "url": "https://github.com/example/core/pull/13",
        }
        with patch.dict(MODULE.os.environ, {}, clear=True):
            sessions, receipt = MODULE.discover_cortex(pr, None)
        self.assertEqual(sessions, [])
        self.assertEqual(receipt["status"], "NOT CONFIGURED")
        self.assertIn("not queried", receipt["reason"])

    def test_cortex_discovery_requires_query_token_without_exposing_it(self):
        pr = {
            "head_branch": "feature", "head_sha": "a" * 40,
            "url": "https://github.com/example/core/pull/13",
        }
        with patch.dict(MODULE.os.environ, {"CORTEX_URL": "https://cortex.invalid"}, clear=True):
            sessions, receipt = MODULE.discover_cortex(pr, None)
        self.assertEqual(sessions, [])
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertNotIn("token=", json.dumps(receipt))


if __name__ == "__main__":
    unittest.main()
