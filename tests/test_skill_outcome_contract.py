from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "skill-outcomes.json"
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RECOVERED_PLUGINS = {
    "yonsei-academic-copilot",
    "yonsei-attendance-copilot",
    "yonsei-shuttle-booking",
    "yonsei-space-reservation",
    "yonsei-yri",
    "yonsei-rms",
    "yonsei-erp",
    "yonsei-groupware",
}


class SkillOutcomeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_has_unique_plugins_and_skills(self) -> None:
        self.assertEqual("yonsei-skill-outcomes/v1", self.contract["schema"])
        plugins = self.contract["plugins"]
        plugin_names = [plugin["plugin"] for plugin in plugins]
        self.assertEqual(len(plugin_names), len(set(plugin_names)))

        skill_names: list[str] = []
        for plugin in plugins:
            self.assertIn(plugin["installation"], {"AVAILABLE", "NOT_AVAILABLE"})
            for outcome in plugin["outcomes"]:
                skill = outcome["skill"]
                self.assertRegex(skill, SKILL_NAME)
                self.assertTrue(outcome["primary_result"].strip())
                self.assertTrue(outcome["state"].strip())
                skill_names.append(skill)
        self.assertEqual(len(skill_names), len(set(skill_names)))

    def test_implemented_outcomes_are_self_contained_skills(self) -> None:
        for plugin in self.contract["plugins"]:
            for outcome in plugin["outcomes"]:
                if outcome["state"] != "implemented":
                    continue
                skill = (
                    ROOT
                    / "plugins"
                    / plugin["plugin"]
                    / "skills"
                    / outcome["skill"]
                )
                self.assertTrue(skill.is_dir(), skill)
                self.assertTrue((skill / "SKILL.md").is_file(), skill)
                self.assertTrue((skill / "agents" / "openai.yaml").is_file(), skill)
                scripts = list((skill / "scripts").glob("*"))
                self.assertTrue(any(path.is_file() for path in scripts), skill)

    def test_not_available_plugins_do_not_claim_implemented_outcomes(self) -> None:
        for plugin in self.contract["plugins"]:
            if (
                plugin["release"] != "not-available"
                or plugin["installation"] != "NOT_AVAILABLE"
            ):
                continue
            self.assertFalse(
                any(
                    outcome["state"] == "implemented"
                    for outcome in plugin["outcomes"]
                ),
                plugin["plugin"],
            )

    def test_recovered_plugins_remain_installable_and_result_specific(self) -> None:
        by_name = {
            plugin["plugin"]: plugin
            for plugin in self.contract["plugins"]
        }
        self.assertEqual(RECOVERED_PLUGINS, RECOVERED_PLUGINS & set(by_name))
        for name in sorted(RECOVERED_PLUGINS):
            plugin = by_name[name]
            self.assertEqual("AVAILABLE", plugin["installation"], name)
            implemented = {
                outcome["skill"]
                for outcome in plugin["outcomes"]
                if outcome["state"] == "implemented"
            }
            self.assertGreaterEqual(len(implemented), 3, name)
            self.assertNotIn(name, implemented)
            self.assertTrue(
                all(
                    (ROOT / "plugins" / name / "skills" / skill / "SKILL.md").is_file()
                    for skill in implemented
                ),
                name,
            )


if __name__ == "__main__":
    unittest.main()
