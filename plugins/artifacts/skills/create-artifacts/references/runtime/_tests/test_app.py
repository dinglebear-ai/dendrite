import json
import tempfile
import unittest
from pathlib import Path

from _app.catalog import CATEGORIES, load_catalog
from _app.render import render_index, render_viewer

ROOT = Path(__file__).resolve().parent.parent

def fixture_root(directory):
    root = Path(directory)
    donor = '<style>:root{--b1:#fff;--b2:#eee;--b3:#ddd;--bc:#111;--muted:#666;--p:#f50;--pc:#fff;--info:#27f;--ok:#292;--warn:#b70;--err:#c22;--mono:monospace;--body:sans-serif}</style><header class="top">top</header><footer>foot</footer>'
    valid = '<title>Core — Audit</title><meta name="artifact.id" content="audit"><meta name="artifact.status" content="accepted"><meta name="artifact.date" content="2026-08-28"><meta name="artifact.topic" content="demo"><div class="eyebrow">Core / report</div><p>Useful description.</p><aside class="verified"><strong>yes</strong></aside><div class="num">1</div><div class="label">fact</div>' + donor
    for category in CATEGORIES:
        folder = root / category
        folder.mkdir()
        (folder / "CLAUDE.md").write_text("# Folder\n\nFolder description.")
        (folder / "_template.html").write_text(valid)
    (root / "reports" / "audit.html").write_text(valid)
    (root / "scripts" / "prove.sh").write_text("#!/bin/sh\n# proof script\necho ok\n")
    (root / "scripts" / "test_hidden.py").write_text("bad")
    (root / "index-meta.json").write_text(json.dumps({"order": ["reports/audit.html"]}))
    return root

class ArtifactAppTest(unittest.TestCase):
    def test_catalog_excludes_templates_and_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = load_catalog(fixture_root(directory))
            self.assertEqual([i["href"] for i in catalog["items"]], ["reports/audit.html", "scripts/prove.sh"])
            self.assertIn("pr-reports", {group["name"] for group in catalog["groups"]})

    def test_catalog_discovers_repository_scoped_pr_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture_root(directory)
            target = root / "pr-reports" / "unraid-core"
            target.mkdir()
            source = (root / "pr-reports" / "_template.html").read_text()
            target.joinpath("codex-fix-auth.html").write_text(source)
            hrefs = {item["href"] for item in load_catalog(root)["items"]}
            self.assertIn("pr-reports/unraid-core/codex-fix-auth.html", hrefs)

    def test_validation_reports_malformed_and_unlisted_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture_root(directory)
            (root / "reports" / "broken.html").write_text("<title>Broken</title>")
            messages = [i["message"] for i in load_catalog(root)["issues"]]
            self.assertTrue(any("missing eyebrow" in message for message in messages))
            self.assertTrue(any("not ordered" in message for message in messages))

    def test_live_and_static_modes_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = load_catalog(fixture_root(directory))
            live, static = render_index(catalog, True), render_index(catalog, False)
            self.assertIn("Live discovery", live)
            self.assertIn("/events", live)
            self.assertIn("/view/scripts/prove.sh", live)
            self.assertIn("Static export", static)
            self.assertIn("LIVE ENDPOINTS REQUIRE APP.PY", static)
            self.assertNotIn("/view/scripts/prove.sh", static)
            self.assertIn('id="search"', live)

    def test_viewer_renders_markdown_and_numbered_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture_root(directory)
            (root / "docs" / "readme.md").write_text("# Heading\n\nText")
            catalog = load_catalog(root)
            self.assertIn("<h1>Heading</h1>", render_viewer(root, "docs/readme.md", catalog))
            source = render_viewer(root, "scripts/prove.sh", catalog, "source")
            self.assertIn('id="L1"', source)
            self.assertIn(">Copy<", source)
            with self.assertRaises(FileNotFoundError):
                render_viewer(root, "../outside", catalog)

    def test_topic_relationships_are_bidirectional(self):
        with tempfile.TemporaryDirectory() as directory:
            root = fixture_root(directory)
            second = (root / "proposals" / "proposal.html")
            second.write_text((root / "reports" / "audit.html").read_text().replace("content=\"audit\"", "content=\"proposal\""))
            items = load_catalog(root)["items"]
            report = next(i for i in items if i["href"] == "reports/audit.html")
            self.assertIn("proposals/proposal.html", {i["href"] for i in report["related"]})

    def test_current_package_is_serializable_and_has_no_test_artifact(self):
        catalog = load_catalog(ROOT)
        hrefs = {item["href"] for item in catalog["items"]}
        self.assertNotIn("scripts/test_artifact_app.py", hrefs)
        self.assertIn("pr-reports", {group["name"] for group in catalog["groups"]})
        for name in ("AGENTS.md", "GEMINI.md"):
            path = ROOT / "pr-reports" / name
            self.assertTrue(path.is_symlink())
            self.assertEqual(path.resolve(), (ROOT / "pr-reports" / "CLAUDE.md").resolve())
        json.dumps(catalog["issues"])

if __name__ == "__main__": unittest.main()
