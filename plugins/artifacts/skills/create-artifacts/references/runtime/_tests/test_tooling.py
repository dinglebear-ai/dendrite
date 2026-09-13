"""Tests for the modules that parse: shell, theme, typography, highlight, plans.

These carry the trickiest logic in the repository — masking fenced code before
reading structure, matching fences of differing length, tokenizing, and writing
idempotent style blocks. Every case below is a bug this code actually had.
"""
import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from _app import highlight, theme, typography  # noqa: E402
from _app.search import plain_text, search  # noqa: E402
from _app.shell import _outline, _outline_html, _split, local_fonts, render_shell  # noqa: E402

_spec = importlib.util.spec_from_file_location("render_plan", ROOT / "scripts" / "render-plan.py")
render_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_plan)

_styles = importlib.util.spec_from_file_location("apply_styles", ROOT / "scripts" / "apply-styles.py")
apply_styles = importlib.util.module_from_spec(_styles)
_styles.loader.exec_module(apply_styles)


ARTIFACT = (
    '<!doctype html><html lang="en"><head><title>Core — Demo</title>'
    '<style>:root{--b1:#fff;--bc:#111;--mono:monospace;--body:sans-serif}'
    '.eyebrow{font:650 11px var(--mono)}</style></head>'
    '<body><div class="shell"><header class="top">chrome</header>'
    '<main><div class="eyebrow">Area / thing</div><p>A description.</p></main>'
    "</div></body></html>"
)


class HighlightTest(unittest.TestCase):
    def test_marks_keywords_strings_and_comments(self):
        out = highlight.highlight('def f():\n    # note\n    return "x"', "python")
        self.assertIn('<span class="k">def</span>', out)
        self.assertIn('<span class="c"># note</span>', out)
        self.assertIn('<span class="s">&quot;x&quot;</span>', out)

    def test_escapes_markup_in_code(self):
        out = highlight.highlight("a < b && c > d", "python")
        self.assertNotIn("<b", out)
        self.assertIn("&lt;", out)

    def test_unknown_language_is_escaped_but_untokenized(self):
        out = highlight.highlight("def <x>", "brainfuck")
        self.assertEqual(out, "def &lt;x&gt;")

    def test_aliases_resolve(self):
        self.assertIn('class="k"', highlight.highlight("def f(): pass", "py"))
        self.assertIn('class="k"', highlight.highlight("if true; then :; fi", "sh"))


class PlanParsingTest(unittest.TestCase):
    """Every case here is a bug the renderer shipped at least once."""

    def test_task_headings_inside_fences_are_not_tasks(self):
        source = (
            "# X Implementation Plan\n\n**Goal:** g\n\n"
            "### Task 1: real\n\n- [ ] **Step 1: a**\n\n"
            "```markdown\n### Task 9: quoted, not real\n- [ ] **Step 1: no**\n```\n"
        )
        plan = render_plan.parse(source)
        self.assertEqual([t["name"] for t in plan["tasks"]], ["real"])
        self.assertEqual(len(plan["tasks"][0]["steps"]), 1)

    def test_a_longer_closing_fence_still_closes(self):
        # CommonMark allows the closing fence to be longer. A strict backreference
        # left the block open and swallowed every task after it.
        # The failure needs a later fence for a strict backreference to pair with:
        # it then masks everything between, and Task 2 disappears.
        source = (
            "# X Implementation Plan\n\n### Task 1: one\n\n- [ ] **Step 1: a**\n\n"
            "````python\na\n`````\n\n### Task 2: two\n\n- [ ] **Step 1: b**\n\n"
            "````elixir\nb\n````\n"
        )
        self.assertEqual([t["name"] for t in render_plan.parse(source)["tasks"]], ["one", "two"])

    def test_a_nested_fence_does_not_close_its_parent(self):
        source = (
            "# X Implementation Plan\n\n### Task 1: one\n\n- [ ] **Step 1: a**\n\n"
            "````markdown\n```python\nx = 1\n```\n````\n\n### Task 2: two\n\n"
            "- [ ] **Step 1: b**\n"
        )
        plan = render_plan.parse(source)
        self.assertEqual([t["name"] for t in plan["tasks"]], ["one", "two"])
        self.assertIn("```python", plan["tasks"][0]["steps"][0]["code"][0][1])

    def test_checkbox_state_drives_progress(self):
        source = ("# X Implementation Plan\n\n### Task 1: one\n\n"
                  "- [x] **Step 1: a**\n\n- [ ] **Step 2: b**\n")
        steps = render_plan.parse(source)["tasks"][0]["steps"]
        self.assertEqual([s["done"] for s in steps], [True, False])

    def test_front_matter_becomes_metadata(self):
        source = "---\nartifact.status: draft\nartifact.topic: core\n---\n\n# X Implementation Plan\n"
        self.assertEqual(render_plan.parse(source)["meta"],
                         {"status": "draft", "topic": "core"})

    def test_step_prose_drops_the_task_separator(self):
        source = ("# X Implementation Plan\n\n### Task 1: one\n\n"
                  "- [ ] **Step 1: a**\n\nRun it.\n\n---\n")
        self.assertEqual(render_plan.parse(source)["tasks"][0]["steps"][0]["prose"], "Run it.")

    def test_fence_language_is_captured_for_highlighting(self):
        source = ("# X Implementation Plan\n\n### Task 1: one\n\n"
                  "- [ ] **Step 1: a**\n\n```elixir\n:ok\n```\n")
        self.assertEqual(render_plan.parse(source)["tasks"][0]["steps"][0]["code"],
                         [("elixir", ":ok")])

    def test_step_kinds_cover_the_tdd_cycle(self):
        kinds = [render_plan.step_kind(t) for t in (
            "Step 1: Write the failing test", "Step 2: Run the test to verify it fails",
            "Step 3: Write the minimal implementation",
            "Step 4: Run the test to verify it passes", "Step 5: Commit")]
        self.assertEqual(kinds, ["test", "expect-fail", "implement", "expect-pass", "commit"])

    def test_file_verbs_become_badges(self):
        self.assertIn('class="verb new"', render_plan.render_file("Create: `a.py`"))
        self.assertIn('class="verb edit"', render_plan.render_file("Modify: `a.py:1-2`"))
        self.assertNotIn("verb", render_plan.render_file("Something else entirely"))


class ShellTest(unittest.TestCase):
    def test_split_removes_the_artifacts_own_header(self):
        styles, body = _split(ARTIFACT)
        self.assertIn("--mono:monospace", styles)
        self.assertNotIn('<header class="top">', body)
        self.assertIn('class="eyebrow"', body)

    def test_split_preserves_artifact_header_controls(self):
        artifact = ARTIFACT.replace(
            '<header class="top">chrome</header>',
            '<header class="top"><div class="brand">chrome</div>'
            '<div class="top-actions"><div class="density-controls">'
            '<button data-density="reviewer">Reviewer</button></div>'
            '<button data-public-mode>Preview public-safe fields</button></div></header>',
        )

        _, body = _split(artifact)

        self.assertNotIn('<header class="top">', body)
        self.assertIn('class="top-actions wb-artifact-actions"', body)
        self.assertIn('data-density="reviewer"', body)
        self.assertIn("data-public-mode", body)
        self.assertNotIn('class="brand"', body)

    def test_shell_frames_the_enriched_artifact(self):
        catalog = {
            "groups": [{"name": "reports", "items": [
                {"href": "reports/a.html", "title": "A", "status": "accepted",
                 "topic": "t", "meta": {}, "related": [], "source": ARTIFACT}]}],
            "items": [{"href": "reports/a.html", "source": ARTIFACT}],
        }
        item = catalog["groups"][0]["items"][0]
        page = render_shell(catalog, item, "clean", ARTIFACT.replace("</main>", "<p>extra</p></main>"))
        self.assertIn("<p>extra</p>", page)          # enrichment survives the wrap
        self.assertIn('class="wb-side"', page)
        self.assertNotIn('<header class="top">', page)

    def test_scripts_drawer_starts_closed_and_others_open(self):
        def group(name):
            return {"name": name, "items": [
                {"href": f"{name}/a.html", "title": "A", "status": "accepted",
                 "topic": "t", "meta": {}, "related": [], "source": ARTIFACT}]}
        catalog = {"groups": [group("reports"), group("scripts")],
                   "items": [{"href": "reports/a.html", "source": ARTIFACT}]}
        page = render_shell(catalog, catalog["groups"][0]["items"][0])
        self.assertIn('data-group="reports" open', page)
        self.assertIn('data-group="scripts">', page)


class OutlineTest(unittest.TestCase):
    FINDINGS = (
        '<details class="issue"><summary><h3>First</h3>'
        '<span class="tag high">High</span></summary>body</details>'
        '<details class="issue" id="kept"><summary><h3>Second</h3>'
        '<span class="tag runtime">Runtime</span></summary>body</details>'
    )

    def test_ids_are_injected_only_where_missing(self):
        body, entries = _outline(self.FINDINGS)
        self.assertEqual([e["id"] for e in entries], ["f1", "kept"])
        self.assertEqual(body.count('id="kept"'), 1)

    def test_severity_drives_the_dot(self):
        _, entries = _outline(self.FINDINGS)
        self.assertEqual([e["dot"] for e in entries], ["err", "ok"])

    def test_titles_are_plain_text(self):
        _, entries = _outline('<details class="issue"><summary>'
                              '<h3>A <span class="mono">path</span></h3></summary>x</details>'
                              + self.FINDINGS)
        self.assertEqual(entries[0]["title"], "A path")

    def test_a_single_finding_gets_no_outline(self):
        _, entries = _outline('<details class="issue"><summary><h3>Only</h3></summary>x</details>')
        self.assertEqual(_outline_html(entries), "")

    def test_font_sources_are_rewritten_for_http(self):
        css = '@font-face{src:url("file:///Users/x/priv/static/fonts/inter-vf-normal-latin.woff2")}'
        self.assertIn('url("/assets/fonts/inter-vf-normal-latin.woff2")', local_fonts(css))
        self.assertNotIn("file://", local_fonts(css))


class RelatedResolutionTest(unittest.TestCase):
    """A relation naming a plan's Markdown must resolve to the plan's card."""

    def test_generated_source_resolves_to_its_artifact(self):
        from _app.catalog import load_catalog

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("plans", "sessions"):
                (root / name).mkdir()
                (root / name / "CLAUDE.md").write_text("# F\n\nDescription.")
            (root / "plans" / "p.md").write_text(
                "---\nartifact.id: p\nartifact.status: draft\n"
                "artifact.date: 2026-08-28\nartifact.topic: t\n---\n# Plan\n\nBody.\n")
            page = (
                '<title>Core — P</title><meta name="artifact.generated" content="p.md">'
                '<meta name="artifact.id" content="ph"><meta name="artifact.status" content="draft">'
                '<meta name="artifact.date" content="2026-08-28">'
                '<meta name="artifact.topic" content="t">'
                '<div class="eyebrow">a / b</div><p>Desc.</p>'
                '<aside class="verified"><strong>x</strong></aside>'
                '<div class="num">1</div><div class="label">f</div>'
                "<style>:root{--b1:#fff}</style><header class=\"top\">t</header><footer>f</footer>"
            )
            (root / "plans" / "p.html").write_text(page)
            (root / "sessions" / "s.html").write_text(
                page.replace('content="p.md"', 'content=""')
                    .replace('content="ph"', 'content="sh"')
                + '<meta name="artifact.related" content="plans/p.md">')

            catalog = load_catalog(root)
            missing = [i for i in catalog["issues"] if i.get("rule") == "RELATED-MISSING"]
            self.assertEqual(missing, [], "a link to the plan source should resolve")


class SearchTest(unittest.TestCase):
    def test_plain_text_drops_markup_and_scripts(self):
        lines = plain_text('<style>.a{x:y}</style><p>Hello there</p><script>bad()</script>')
        self.assertIn("Hello there", lines)
        self.assertFalse(any("bad()" in l or "x:y" in l for l in lines))

    def test_matches_are_marked_and_ranked(self):
        catalog = {"items": [
            {"href": "a.html", "title": "A", "blurb": "", "source": "<p>one symlink here</p>"},
            {"href": "b.html", "title": "B", "blurb": "",
             "source": "<p>symlink</p><p>symlink again</p>"},
        ]}
        results = search(catalog, "symlink")
        self.assertEqual([r["href"] for r in results], ["b.html", "a.html"])
        self.assertIn("\x00symlink\x01", results[0]["lines"][0])

    def test_short_queries_are_ignored(self):
        self.assertEqual(search({"items": []}, "a"), [])


class StyleBlockTest(unittest.TestCase):
    def test_apply_is_idempotent(self):
        once, changed = apply_styles.apply(ARTIFACT)
        self.assertTrue(changed)
        twice, changed_again = apply_styles.apply(once)
        self.assertFalse(changed_again)
        self.assertEqual(once, twice)

    def test_both_blocks_land_and_light_is_unpinned(self):
        out, _ = apply_styles.apply(ARTIFACT.replace('<html lang="en">',
                                                     '<html lang="en" data-theme="light">'))
        self.assertIn(theme.MARK_OPEN, out)
        self.assertIn(typography.MARK_OPEN, out)
        self.assertNotIn('data-theme="light"', out)

    def test_typography_is_the_last_word_in_the_sheet(self):
        out, _ = apply_styles.apply(ARTIFACT)
        self.assertLess(out.index(".eyebrow{font:650 11px var(--mono)}"),
                        out.index(typography.MARK_OPEN))
        self.assertLess(out.index(typography.MARK_OPEN), out.index("</style>"))

    def test_theme_defines_every_light_token(self):
        light = set(re.findall(r"(--[\w-]+):", re.search(r":root\{(.*?)\}", ARTIFACT, re.S).group(1)))
        dark = set(re.findall(r"(--[\w-]+):", theme.DARK_TOKENS))
        self.assertTrue(light <= dark | {"--body", "--mono"},
                        f"dark palette misses {light - dark}")

    def test_code_selectors_keep_the_mono_face(self):
        for selector in (".evidence", ".code", ".mono", "pre", "code"):
            self.assertIn(selector, typography.CSS.split("stay monospace")[1])


if __name__ == "__main__":
    unittest.main()
