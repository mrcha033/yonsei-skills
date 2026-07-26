from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"


class PackagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))

    def test_each_entry_is_independent_and_matching(self) -> None:
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
            self.assertEqual([plugin / "skills" / name], skill_dirs)
            self.assertFalse(any(path.is_symlink() for path in plugin.rglob("*")))
            for path in plugin.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("/Users/", text)
                self.assertNotIn("../plugins/", text)
                self.assertNotIn("yonsei-portal-copilot", text)

    def test_marketplace_policy(self) -> None:
        self.assertEqual("yonsei-skills", self.marketplace["name"])
        for entry in self.marketplace["plugins"]:
            self.assertEqual("AVAILABLE", entry["policy"]["installation"])
            self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])
            self.assertEqual("Education", entry["category"])
            self.assertEqual(
                f"./plugins/{entry['name']}",
                entry["source"]["path"],
            )

    def test_runtime_plugins_work_outside_repo(self) -> None:
        import shutil
        import subprocess
        import sys

        plugins = [
            entry["name"]
            for entry in self.marketplace["plugins"]
            if entry["name"] != "learnus-course-copilot"
        ]
        with tempfile.TemporaryDirectory(prefix="yonsei-plugin-isolation-") as temp:
            for name in plugins:
                source = ROOT / "plugins" / name
                target = Path(temp) / name
                shutil.copytree(source, target)
                skill = target / "skills" / name
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(skill / "scripts" / "yonsei_service.py"),
                        "doctor",
                        "--json",
                    ],
                    cwd=temp,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, f"{name}: {completed.stderr}")
                self.assertEqual("ok", json.loads(completed.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
