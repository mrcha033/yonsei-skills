from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
CLAUDE_MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
OUTCOMES = ROOT / "contracts" / "skill-outcomes.json"
FRONTMATTER_NAME = re.compile(r"^name:\s*([a-z0-9-]+)\s*$", re.MULTILINE)


class PackagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        contract = json.loads(OUTCOMES.read_text(encoding="utf-8"))
        self.outcomes = {
            plugin["plugin"]: plugin
            for plugin in contract["plugins"]
        }

    def test_each_entry_is_independent_and_matching(self) -> None:
        self.assertNotIn(
            "/Users/",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
        for entry in self.marketplace["plugins"]:
            name = entry["name"]
            plugin = ROOT / "plugins" / name
            manifest = json.loads(
                (plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual(name, manifest["name"])
            skill_dirs = sorted(
                path.parent
                for path in (plugin / "skills").glob("*/SKILL.md")
            )
            packaged_names: set[str] = set()
            for skill_dir in skill_dirs:
                skill_name = skill_dir.name
                packaged_names.add(skill_name)
                text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                match = FRONTMATTER_NAME.search(text)
                self.assertIsNotNone(match, skill_dir)
                self.assertEqual(skill_name, match.group(1), skill_dir)
                self.assertTrue((skill_dir / "agents" / "openai.yaml").is_file())
            contract = self.outcomes[name]
            if contract["release"] != "external-user-work":
                declared = {
                    outcome["skill"]
                    for outcome in contract["outcomes"]
                    if outcome["state"] == "implemented"
                }
                self.assertEqual(declared, packaged_names, name)
            self.assertFalse(any(path.is_symlink() for path in plugin.rglob("*")))
            for path in plugin.rglob("*"):
                if not path.is_file():
                    continue
                if "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("/Users/", text)
                self.assertNotIn("../plugins/", text)
                self.assertNotIn("yonsei-portal-copilot", text)

    def test_marketplace_policy(self) -> None:
        self.assertEqual("yonsei-skills", self.marketplace["name"])
        claude = json.loads(CLAUDE_MARKETPLACE.read_text(encoding="utf-8"))
        claude_names = {entry["name"] for entry in claude["plugins"]}
        expected_claude_names: set[str] = set()
        for entry in self.marketplace["plugins"]:
            expected = self.outcomes[entry["name"]]["installation"]
            self.assertEqual(expected, entry["policy"]["installation"])
            if expected == "AVAILABLE":
                expected_claude_names.add(entry["name"])
            self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])
            self.assertEqual("Education", entry["category"])
            self.assertEqual(
                f"./plugins/{entry['name']}",
                entry["source"]["path"],
            )
        self.assertEqual(expected_claude_names, claude_names)

    def test_runtime_plugins_work_outside_repo(self) -> None:
        import shutil
        import subprocess
        import sys

        plugins = [entry["name"] for entry in self.marketplace["plugins"]]
        with tempfile.TemporaryDirectory(prefix="yonsei-plugin-isolation-") as temp:
            for name in plugins:
                source = ROOT / "plugins" / name
                target = Path(temp) / name
                shutil.copytree(source, target)
                scripts = sorted(
                    path
                    for path in target.rglob("*.py")
                    if "__pycache__" not in path.parts
                )
                self.assertTrue(scripts, name)
                for script in scripts:
                    completed = subprocess.run(
                        [sys.executable, "-B", str(script), "--help"],
                        cwd=target,
                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=30,
                    )
                    self.assertEqual(
                        0,
                        completed.returncode,
                        f"{name}/{script.relative_to(target)}: {completed.stderr}",
                    )


if __name__ == "__main__":
    unittest.main()
