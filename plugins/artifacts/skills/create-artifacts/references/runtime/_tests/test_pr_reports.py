import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
DATE = datetime.now().strftime("%m-%d-%y")

ROOT = Path(__file__).resolve().parent.parent
PYTHON = "python3"


class PrReportScriptsTest(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        templates = root / "pr-reports"
        templates.mkdir()
        templates.joinpath("_template.html").write_text(
            (ROOT / "pr-reports/_template.html").read_text())
        root.joinpath("index-meta.json").write_text('{"order": []}')
        return root

    def create(self, root, branch="codex/fix-auth", sha="a" * 40):
        return subprocess.run([
            PYTHON, str(ROOT / "scripts/new-pr-report.py"),
            "--root", str(root), "--repository", "unraid/core",
            "--branch", branch, "--base", "main @ " + "b" * 40,
            "--head-sha", sha, "--merge-base", "c" * 40,
            "--worktree", str(root / "worktree"), "--topic", "auth",
            "--allow-unverified",
        ], text=True, capture_output=True)

    def test_generator_populates_identity_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            first = self.create(root)
            self.assertEqual(first.returncode, 0, first.stderr)
            report = root / f"unraid-core/pr-reports/{DATE}-codex-fix-auth.html"
            self.assertTrue(report.exists())
            self.assertIn('content="unraid/core"', report.read_text())
            second = self.create(root)
            self.assertNotEqual(second.returncode, 0)

    def test_normalization_collision_uses_head_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            self.assertEqual(self.create(root, "codex/fix-auth", "a" * 40).returncode, 0)
            collision = self.create(root, "codex-fix/auth", "d" * 40)
            self.assertEqual(collision.returncode, 0, collision.stderr)
            self.assertTrue((root / f"unraid-core/pr-reports/{DATE}-codex-fix-auth--dddddddd.html").exists())
            existing_suffix = self.create(root, "codex.fix/auth", "d" * 40)
            self.assertNotEqual(existing_suffix.returncode, 0)

    def test_malformed_manifest_and_implicit_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            self.assertEqual(self.create(root).returncode, 0)
            report = root / f"unraid-core/pr-reports/{DATE}-codex-fix-auth.html"
            manifest = report.with_suffix(".evidence.jsonl")
            manifest.write_text("not json\n")
            evidence = root / "proof.log"
            evidence.write_text("proof\n")
            command = [PYTHON, str(ROOT / "scripts/record-pr-evidence.py"),
                       "--manifest", str(manifest), "--id", "E-001", "--kind", "log",
                       "--file", str(evidence), "--producer", "Codex", "--command", "proof",
                       "--source-sha", "a" * 40, "--cwd", str(root), "--applies-to", "head"]
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(manifest.read_text(), "not json\n")

    def test_capture_rejects_sensitive_environment_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            self.assertEqual(self.create(root).returncode, 0)
            report = root / f"unraid-core/pr-reports/{DATE}-codex-fix-auth.html"
            result = subprocess.run([
                PYTHON, str(ROOT / "scripts/capture-pr-evidence.py"),
                "--manifest", str(report.with_suffix(".evidence.jsonl")), "--id", "E-001",
                "--kind", "log", "--output", str(root / "capture.json"),
                "--producer", "Codex", "--source-sha", "a" * 40,
                "--applies-to", "head", "--cwd", str(root), "--env", "API_TOKEN",
                "--", "printf", "ok"], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "capture.json").exists())

    def test_capture_never_overwrites_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); self.assertEqual(self.create(root).returncode, 0)
            report = root / f"unraid-core/pr-reports/{DATE}-codex-fix-auth.html"
            output = root / "capture.json"; output.write_text("immutable old bytes\n")
            result = subprocess.run([PYTHON, str(ROOT / "scripts/capture-pr-evidence.py"),
                "--manifest", str(report.with_suffix(".evidence.jsonl")), "--id", "E-001",
                "--kind", "log", "--output", str(output), "--producer", "Codex",
                "--source-sha", "a" * 40, "--applies-to", "head", "--cwd", str(root),
                "--", "printf", "new"], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), "immutable old bytes\n")

    def test_expected_nonzero_exit_is_successful_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory); self.assertEqual(self.create(root).returncode,0)
            report=root/f"unraid-core/pr-reports/{DATE}-codex-fix-auth.html"
            result=subprocess.run([PYTHON,str(ROOT/"scripts/capture-pr-evidence.py"),"--manifest",str(report.with_suffix(".evidence.jsonl")),"--id","E-001","--kind","base-reproduction","--output",str(root/"base.json"),"--producer","Codex","--source-sha","b"*40,"--applies-to","base","--cwd",str(root),"--expected-exit","1","--",PYTHON,"-c","raise SystemExit(1)"],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(report.with_suffix(".evidence.jsonl").read_text())["state"],"PASS")

    def test_seal_cli_has_no_validation_bypass(self):
        result=subprocess.run([PYTHON,str(ROOT/"scripts/seal-pr-report.py"),"missing.html","--skip-validation"],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("unrecognized arguments",result.stderr)

    def test_finalizer_uses_recoverable_locked_internal_sealing(self):
        source=(ROOT/"scripts/finalize-pr-report.py").read_text()
        self.assertIn("with locked(manifest)",source)
        self.assertIn("seal_locked(candidate,manifest)",source)
        self.assertIn("verify_locked(candidate,manifest)",source)
        self.assertIn("backup.unlink(missing_ok=True)",source)
        self.assertNotIn("--skip-validation",source)

    def test_evidence_record_and_report_seal_detect_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            result = self.create(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = root / f"unraid-core/pr-reports/{DATE}-codex-fix-auth.html"
            manifest = report.with_suffix(".evidence.jsonl")
            evidence = root / "proof.log"
            evidence.write_text("observed output\n")
            record = subprocess.run([
                PYTHON, str(ROOT / "scripts/record-pr-evidence.py"),
                "--manifest", str(manifest), "--id", "E-001", "--kind", "test-log",
                "--file", str(evidence), "--producer", "Codex", "--command", "run proof",
                "--source-sha", "a" * 40, "--cwd", str(root),
                "--applies-to", "head",
                "--state", "PASS",
            ], text=True, capture_output=True)
            self.assertEqual(record.returncode, 0, record.stderr)
            item = json.loads(manifest.read_text())
            self.assertEqual(item["sha256"], hashlib.sha256(evidence.read_bytes()).hexdigest())
            sync = subprocess.run([PYTHON, str(ROOT / "scripts/sync-pr-report-ledgers.py"), str(report)])
            self.assertEqual(sync.returncode, 0)
            filled = report.read_text().replace('{{full head SHA}}', "a" * 40)
            filled = re.sub(r"\{\{[^{}\n]+\}\}", "None", filled)
            filled = filled.replace('data-state="UNKNOWN"', 'data-state="PASS"').replace(
                'data-public-audit="UNKNOWN"', 'data-public-audit="PASS"')
            report.write_text(filled)
            seal = subprocess.run([PYTHON, str(ROOT / "scripts/seal-pr-report.py"), str(report),
                                   "--root", str(root)])
            self.assertEqual(seal.returncode, 0)
            verify = subprocess.run([PYTHON, str(ROOT / "scripts/seal-pr-report.py"),
                                     str(report), "--verify"])
            self.assertEqual(verify.returncode, 0)
            report.write_text(report.read_text().replace("</title>", " tampered</title>"))
            broken = subprocess.run([PYTHON, str(ROOT / "scripts/seal-pr-report.py"),
                                     str(report), "--verify"])
            self.assertNotEqual(broken.returncode, 0)

    def test_manifest_tampering_breaks_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory); self.assertEqual(self.create(root).returncode, 0)
            report = root / f"unraid-core/pr-reports/{DATE}-codex-fix-auth.html"
            manifest = report.with_suffix(".evidence.jsonl"); evidence = root / "proof.log"; evidence.write_text("proof\n")
            subprocess.run([PYTHON, str(ROOT / "scripts/record-pr-evidence.py"), "--manifest", str(manifest),
                "--id", "E-001", "--kind", "test-log", "--file", str(evidence), "--producer", "Codex",
                "--command", "proof", "--source-sha", "a"*40, "--cwd", str(root), "--applies-to", "head", "--state", "PASS"], check=True)
            subprocess.run([PYTHON, str(ROOT / "scripts/sync-pr-report-ledgers.py"), str(report)], check=True)
            filled = report.read_text().replace('{{full head SHA}}', "a"*40)
            filled = re.sub(r"\{\{[^{}\n]+\}\}", "None", filled).replace('data-state="UNKNOWN"','data-state="PASS"')
            report.write_text(filled); subprocess.run([PYTHON, str(ROOT / "scripts/seal-pr-report.py"), str(report), "--root", str(root)], check=True)
            manifest.write_text(manifest.read_text()+"\n")
            self.assertNotEqual(subprocess.run([PYTHON, str(ROOT / "scripts/seal-pr-report.py"), str(report), "--verify"]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
