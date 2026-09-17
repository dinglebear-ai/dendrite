import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "plugins/scripts/check-skill-frontmatter"
loader = importlib.machinery.SourceFileLoader("check_skill_frontmatter", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class SkillFrontmatterTest(unittest.TestCase):
    def validate(self, frontmatter: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(f"---\n{frontmatter}\n---\n# Skill\n", encoding="utf-8")
            return module.validate_skill(path)

    def test_accepts_space_separated_scalar(self):
        self.assertEqual([], self.validate("name: demo\ndescription: demo\nallowed-tools: Bash Read Grep"))

    def test_accepts_quoted_tool_patterns(self):
        self.assertEqual(
            [],
            self.validate(
                'name: demo\ndescription: demo\nallowed-tools: "Bash(git:*) Bash(rg *) Read"'
            ),
        )

    def test_rejects_yaml_sequence(self):
        errors = self.validate(
            "name: demo\ndescription: demo\nallowed-tools:\n  - Bash\n  - Read"
        )
        self.assertTrue(any("YAML sequence" in error for error in errors))

    def test_rejects_comma_separated_scalar(self):
        errors = self.validate(
            "name: demo\ndescription: demo\nallowed-tools: Bash, Read, Grep"
        )
        self.assertTrue(any("not commas" in error for error in errors))

    def test_allows_commas_inside_a_tool_pattern(self):
        self.assertEqual(
            [],
            self.validate(
                "name: demo\ndescription: demo\nallowed-tools: Bash(tool --pair a,b) Read"
            ),
        )

    def test_accepts_string_metadata_values(self):
        self.assertEqual(
            [],
            self.validate(
                "name: demo\ndescription: demo\nmetadata:\n  author: DrJacky\n  version: 1.0.0"
            ),
        )

    def test_rejects_structured_metadata_values(self):
        for frontmatter in (
            "name: demo\ndescription: demo\nmetadata:\n  tags: [android, kotlin]",
            "name: demo\ndescription: demo\nmetadata:\n  audience:\n    - agents\n    - maintainers",
            "name: demo\ndescription: demo\nmetadata:\n  priority: 1",
        ):
            with self.subTest(frontmatter=frontmatter):
                errors = self.validate(frontmatter)
                self.assertTrue(any("metadata values must be strings" in error for error in errors))

    def test_accepts_inline_json_metadata_with_string_values(self):
        self.assertEqual(
            [],
            self.validate(
                'name: demo\ndescription: demo\nmetadata: {"author":"example","version":"1.0"}'
            ),
        )

    def test_rejects_inline_json_metadata_with_structured_values(self):
        errors = self.validate(
            'name: demo\ndescription: demo\nmetadata: {"tags":["android","kotlin"]}'
        )
        self.assertTrue(any("metadata values must be strings" in error for error in errors))

    def test_repository_first_party_skills_are_portable(self):
        failures = {
            str(path.relative_to(ROOT)): module.validate_skill(path)
            for path in module.first_party_skills(ROOT)
            if module.validate_skill(path)
        }
        self.assertEqual({}, failures)


if __name__ == "__main__":
    unittest.main()
