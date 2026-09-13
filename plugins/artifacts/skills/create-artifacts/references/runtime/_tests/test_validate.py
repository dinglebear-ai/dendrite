"""Unit tests for the consolidated rules in _app/validate.py."""
import sys
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from _app import validate  # noqa: E402

COMPLETE = (
    "<title>Core — Audit</title>"
    '<div class="eyebrow">Core / report</div><p>A description.</p>'
    '<aside class="verified"><strong>yes</strong></aside>'
    '<div class="num">1</div><div class="label">fact</div>'
)
META = ('<meta name="artifact.id" content="a"><meta name="artifact.status" content="accepted">'
        '<meta name="artifact.date" content="2026-08-28">'
        '<meta name="artifact.topic" content="core">')
FINDING = ('<details class="issue"><h3>{title}</h3><div class="evidence">out</div>{limit}</details>')
LIMIT = '<div class="limit">what this does not prove</div>'


class StructureTest(unittest.TestCase):
    def test_reports_each_missing_element(self):
        issues = validate.check_structure("reports/x.html", "<html></html>")
        self.assertEqual(sorted(i["message"] for i in issues), [
            "missing eyebrow", "missing headline statistic", "missing hero description",
            "missing title", "missing verification facts"])
        self.assertTrue(all(i["rule"] == "HTML-STRUCTURE" for i in issues))

    def test_complete_artifact_reports_nothing(self):
        self.assertEqual(validate.check_structure("reports/x.html", COMPLETE), [])


class MetadataTest(unittest.TestCase):
    def test_reads_meta_tags_and_front_matter(self):
        self.assertEqual(validate.read_meta('<meta name="artifact.status" content="draft">'),
                         {"status": "draft"})
        self.assertEqual(validate.read_meta("---\nartifact.status: draft\n---\n# P\n"),
                         {"status": "draft"})

    def test_requires_the_four_fields(self):
        messages = sorted(i["message"] for i in
                          validate.check_metadata(ROOT, "reports/x.html", "<title>x</title>"))
        self.assertEqual(messages, ["missing artifact.date", "missing artifact.id",
                                    "missing artifact.status", "missing artifact.topic"])

    def test_rejects_unknown_status_and_bad_date(self):
        source = ('<meta name="artifact.id" content="a">'
                  '<meta name="artifact.status" content="wip">'
                  '<meta name="artifact.date" content="27-08-2026">'
                  '<meta name="artifact.topic" content="core">')
        rules = sorted(i["rule"] for i in validate.check_metadata(ROOT, "r/x.html", source))
        self.assertEqual(rules, ["META-DATE", "META-STATUS"])

    def test_superseded_must_name_a_successor(self):
        source = META.replace('content="accepted"', 'content="superseded"')
        rules = [i["rule"] for i in validate.check_metadata(ROOT, "r/x.html", source)]
        self.assertIn("META-SUPERSEDED", rules)


class FindingsTest(unittest.TestCase):
    def test_bare_finding_in_a_proof_folder_warns_once_per_file(self):
        source = FINDING.format(title="A claim", limit="") * 3
        issues = validate.check_findings("reports/x.html", source)
        self.assertEqual(len(issues), 1)
        self.assertIn("3 of 3", issues[0]["message"])
        self.assertEqual(issues[0]["rule"], "PROOF-LIMIT")

    def test_requirements_and_rules_owe_no_boundary(self):
        source = FINDING.format(title="A rule", limit="")
        self.assertEqual(validate.check_findings("docs/x.html", source), [])
        self.assertEqual(validate.check_findings("specs/x.html", source), [])

    def test_finding_without_evidence_is_not_a_proof_claim(self):
        self.assertEqual(
            validate.check_findings("reports/x.html",
                                    '<details class="issue"><h3>Row</h3></details>'), [])

    def test_finding_with_a_limit_passes(self):
        self.assertEqual(
            validate.check_findings("reports/x.html", FINDING.format(title="A", limit=LIMIT)), [])


class LocalLinkTest(unittest.TestCase):
    def test_worktree_citations_are_flagged(self):
        source = ('<a href="file:///Users/x/repo/.claude/worktrees/wt-1234/lib/a.ex#L4">a</a>')
        rules = [i["rule"] for i in validate.check_local_links("reports/x.html", source)]
        self.assertIn("EPHEMERAL-CITATION", rules)

    def test_durable_paths_are_not_flagged_as_ephemeral(self):
        source = '<a href="file:///Users/x/repo/lib/a.ex#L4">a</a>'
        rules = [i["rule"] for i in validate.check_local_links("reports/x.html", source)]
        self.assertNotIn("EPHEMERAL-CITATION", rules)


class MarkupTest(unittest.TestCase):
    """Defects that survive every other rule because the page still loads."""

    def rules(self, source):
        return [i["rule"] for i in validate.check_markup("reports/x.html", source)]

    def test_bare_angle_bracket_placeholder_is_flagged(self):
        # The browser parses <name> as an unknown element and shows nothing,
        # so the reader sees "knowledge/.md" and no rule ever complained.
        self.assertIn("SWALLOWED-MARKUP",
                      self.rules("<main><p>knowledge/<name>.md</p></main>"))

    def test_escaped_placeholder_is_not_flagged(self):
        self.assertEqual(self.rules("<main><p>knowledge/&lt;name&gt;.md</p></main>"), [])

    def test_duplicate_closing_tag_is_flagged(self):
        self.assertIn("UNBALANCED-MARKUP", self.rules("<main><div>x</div></main></main>"))

    def test_unclosed_element_is_flagged(self):
        self.assertIn("UNBALANCED-MARKUP", self.rules("<main><div>x</main>"))

    def test_optional_end_tags_are_not_flagged(self):
        # HTML5 closes these with the parent, so omitting them is correct.
        self.assertEqual(self.rules("<main><div><p>hi</div><ul><li>a<li>b</ul></main>"), [])

    def test_svg_children_are_not_placeholders(self):
        self.assertEqual(
            self.rules('<main><svg><path d="M0 0"/><circle r="1"/></svg></main>'), [])

    def test_css_selectors_are_not_markup(self):
        self.assertEqual(self.rules("<style>.a > .b { color: red }</style><main>x</main>"), [])


class PlanTest(unittest.TestCase):
    GOOD = (
        "# Thing Implementation Plan\n\n> superpowers:subagent-driven-development\n\n"
        "**Goal:** Build it.\n\n**Architecture:** One module.\n\n**Tech Stack:** Python.\n\n"
        "## Global Constraints\n\n- Python 3.9.\n\n## File Structure\n\n"
        "| File | Responsibility |\n| --- | --- |\n| `a.py` | Owns it. |\n\n"
        "### Task 1: The thing\n\n**Files:**\n- Create: `a.py`\n\n"
        "**Interfaces:**\n- Produces: `a.run()`\n\n"
        "- [ ] **Step 1: Write the failing test**\n\n```python\nassert True\n```\n\n"
        "- [ ] **Step 2: Run it**\n\n- [ ] **Step 3: Commit**\n"
    )

    def test_a_complete_plan_passes(self):
        self.assertEqual(validate.check_plan("plans/p.md", self.GOOD), [])

    def test_missing_header_and_sections_are_errors(self):
        rules = {i["rule"] for i in validate.check_plan("plans/p.md", "# Plan\n")}
        self.assertEqual(rules, {"PLAN-HEADER", "PLAN-SECTION", "PLAN-TASKS"})

    def test_banned_phrases_are_errors_outside_code(self):
        rules = [i["rule"] for i in validate.check_plan("plans/p.md", self.GOOD + "\nTBD\n")]
        self.assertIn("PLAN-PLACEHOLDER", rules)

    def test_banned_phrases_inside_code_are_data(self):
        quoted = self.GOOD.replace("assert True", 'BANNED = ["TBD", "handle edge cases"]')
        self.assertEqual([i for i in validate.check_plan("plans/p.md", quoted)
                          if i["rule"] == "PLAN-PLACEHOLDER"], [])

    def test_templates_may_quote_banned_phrases(self):
        issues = validate.check_plan("plans/_template.md", self.GOOD + "\nTBD\n", template=True)
        self.assertEqual([i for i in issues if i["rule"] == "PLAN-PLACEHOLDER"], [])

    def test_file_entries_want_a_verb(self):
        loose = self.GOOD.replace("- Create: `a.py`", "- `a.py`")
        self.assertIn("PLAN-FILES", [i["rule"] for i in validate.check_plan("plans/p.md", loose)])


class DesignTokenTest(unittest.TestCase):
    def test_conflicting_values_are_an_error(self):
        issues = validate.check_design_tokens({
            "a.html": "<style>:root{--p:#f50}</style>",
            "b.html": "<style>:root{--p:#f00}</style>"})
        self.assertEqual([i["rule"] for i in issues], ["TOKEN-DRIFT"])

    def test_a_missing_token_is_only_a_warning(self):
        issues = validate.check_design_tokens({
            "a.html": "<style>:root{--p:#f50;--pc:#fff}</style>",
            "b.html": "<style>:root{--p:#f50}</style>"})
        self.assertEqual([(i["severity"], i["rule"]) for i in issues], [("warning", "TOKEN-MISSING")])

    def test_identical_palettes_pass(self):
        self.assertEqual(validate.check_design_tokens({
            "a.html": "<style>:root{--p:#f50}</style>",
            "b.html": "<style>:root{--p:#f50}</style>"}), [])


class ValidateArtifactTest(unittest.TestCase):
    def test_html_runs_structure_metadata_and_ordering(self):
        rules = {i["rule"] for i in
                 validate.validate_artifact(ROOT, "reports/x.html", "<html></html>", [])}
        self.assertIn("HTML-STRUCTURE", rules)
        self.assertIn("META-REQUIRED", rules)
        self.assertIn("INDEX-ORDER", rules)

    def test_generated_output_skips_authoring_rules(self):
        source = (COMPLETE + META + '<meta name="artifact.generated" content="x.md">'
                  + FINDING.format(title="A claim", limit=""))
        rules = {i["rule"] for i in
                 validate.validate_artifact(ROOT, "plans/x.html", source, ["plans/x.html"])}
        self.assertNotIn("PROOF-LIMIT", rules)

    def test_markdown_in_plans_runs_the_plan_contract(self):
        rules = {i["rule"] for i in
                 validate.validate_artifact(ROOT, "plans/p.md", "# Plan\n", [])}
        self.assertIn("PLAN-TASKS", rules)

    def test_templates_are_exempt_from_metadata_and_placeholders(self):
        rules = {i["rule"] for i in
                 validate.validate_artifact(ROOT, "reports/_template.html", COMPLETE, [])}
        self.assertEqual(rules, set())

    def test_surviving_template_placeholders_are_errors(self):
        template = COMPLETE + "<p>[One sentence describing the finding]</p>"
        source = COMPLETE + META + "<p>[One sentence describing the finding]</p>"
        rules = [i["rule"] for i in validate.validate_artifact(
            ROOT, "reports/x.html", source, ["reports/x.html"], template)]
        self.assertIn("PLACEHOLDER", rules)


class PrReportTest(unittest.TestCase):
    def test_canonical_template_implements_every_required_section(self):
        source = (ROOT / "pr-reports" / "_template.html").read_text()
        self.assertEqual(
            [name for name in validate.PR_REPORT_SECTIONS if f'id="{name}"' not in source],
            [])
        report_template = (ROOT / "reports" / "_template.html").read_text()
        self.assertEqual(validate.check_design_tokens({
            "reports/_template.html": report_template,
            "pr-reports/_template.html": source,
        }), [])

    def test_path_is_repository_scoped_and_branch_named(self):
        rules = {i["rule"] for i in validate.check_pr_report(
            "pr-reports/unraid-core/codex-fix-auth.html", "")}
        self.assertNotIn("PR-PATH", rules)
        self.assertIn("PR-METADATA", rules)
        bad = {i["rule"] for i in validate.check_pr_report("pr-reports/bad/path/extra.html", "")}
        self.assertIn("PR-PATH", bad)

    def test_template_section_contract_is_machine_checkable(self):
        source = (ROOT / "pr-reports" / "_template.html").read_text()
        for field, value in (("schema-version", "2"), ("revision", "1"),
                                 ("repository", "unraid/core"), ("base", "main @ " + "a" * 40),
                                 ("branch", "codex/fix-auth"),
                                 ("head", "codex/fix-auth @ " + "b" * 40),
                                 ("target", "b" * 40), ("pr", "url"),
                                 ("merge-base", "c" * 40),
                                 ("started", "2026-08-30T04:00:00-04:00"),
                                 ("updated", "2026-08-30T04:00:00-04:00"),
                                 ("worktree", "/path"),
                                 ("evidence-manifest", "/path/evidence.jsonl"),
                                 ("evidence-manifest-digest", "UNSEALED"),
                                 ("report-digest", "UNSEALED"),
                                 ("provenance-status", "VERIFIED")):
            source = re.sub(r'(<meta name="artifact\.' + re.escape(field) +
                            r'" content=")[^"]*(">)', r'\g<1>' + value + r'\2', source)
        source = source.replace('{{full head SHA}}', "b" * 40)
        self.assertEqual(validate.check_pr_report(
            "pr-reports/unraid-core/codex-fix-auth.html", source), [])

    def test_repository_and_head_must_match_path(self):
        source = ('<meta name="artifact.repository" content="unraid/core-plugins">'
                  '<meta name="artifact.head" content="codex/other @ deadbeef">')
        rules = {i["rule"] for i in validate.check_pr_report(
            "pr-reports/unraid-core/codex-fix-auth.html", source)}
        self.assertIn("PR-REPOSITORY", rules)
        self.assertIn("PR-BRANCH", rules)

    def test_pr_reports_reject_new_prompts_not_in_template(self):
        issues = validate.check_placeholders(
            "pr-reports/unraid-core/x.html", "<p>{{verify later}}</p>", "<p>{{known}}</p>")
        self.assertEqual(issues[0]["rule"], "PLACEHOLDER")

    def test_branch_name_containing_template_does_not_bypass_prompts(self):
        issues = validate.check_placeholders(
            "pr-reports/unraid-core/codex-template-fix.html", "<p>{{unfinished}}</p>", "")
        self.assertEqual(issues[0]["rule"], "PLACEHOLDER")

    def test_every_stable_and_governed_data_row_is_structured(self):
        source = (ROOT / "pr-reports" / "_template.html").read_text()
        source = source.replace('data-record-id="TEST-001" ', "", 1)
        source = source.replace('data-state="UNKNOWN"', "", 1)
        rules = {item["rule"] for item in validate.check_pr_report(
            "pr-reports/unraid-core/codex-fix-auth.html", source)}
        self.assertIn("PR-ID", rules)
        self.assertIn("PR-STATE", rules)


if __name__ == "__main__":
    unittest.main()
