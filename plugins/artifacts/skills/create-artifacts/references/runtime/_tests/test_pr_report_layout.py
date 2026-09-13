import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr_report_layout", ROOT / "scripts" / "redesign-pr-report-layout.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrReportLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "pr-reports" / "_template.html").read_text()

    def test_reviewer_route_preserves_exact_section_denominator(self):
        rendered = MODULE.transform(self.template)
        self.assertEqual(rendered.count('<details id="'), 29)
        self.assertEqual(rendered.count('class="phasehead"'), 6)
        for slug, _, _, section_ids in MODULE.STAGES:
            self.assertIn(f'id="phase-{slug}"', rendered)
            for section_id in section_ids:
                self.assertEqual(rendered.count(f'id="{section_id}"'), 1)

    def test_all_review_control_surfaces_are_present(self):
        rendered = MODULE.transform(self.template)
        for marker in (
            'data-public-mode', 'data-posture', 'data-proven', 'data-blockers',
            'data-next', 'data-filter="unresolved"', 'data-filter="changed"',
            'Executive change map', 'Since the last review', 'freshness',
            'evidence-uses', 'action-needed', 'sort-button', 'public-preview',
        ):
            self.assertIn(marker, rendered)

    def test_machine_manifest_is_read_after_document_parsing(self):
        rendered = MODULE.transform(self.template)
        self.assertIn(
            'addEventListener("DOMContentLoaded",()=>{const machineTag=', rendered
        )

    def test_responsive_control_deck_override_follows_desktop_grid(self):
        rendered = MODULE.transform(self.template)
        desktop = '.control-deck{grid-template-columns:repeat(2,minmax(0,1fr))}'
        responsive = '@media(max-width:900px){.control-deck{grid-template-columns:1fr}}'
        self.assertGreater(rendered.rfind(responsive), rendered.rfind(desktop))

    def test_transform_is_idempotent(self):
        once = MODULE.transform(self.template)
        twice = MODULE.transform(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
