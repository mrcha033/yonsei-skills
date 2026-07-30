import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_release_packages.py"
SPEC = importlib.util.spec_from_file_location("build_release_packages", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReleasePackageTests(unittest.TestCase):
    def build(self, output: Path) -> None:
        MODULE.build(output, "9.8.7")

    def test_builds_stable_click_first_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.build(output)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted((*MODULE.ARCHIVES, "SHA256SUMS.txt")),
            )

    def test_codex_pack_has_student_marketplace_and_plugins(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.build(output)
            with zipfile.ZipFile(output / "yonsei-codex-ui-pack.zip") as archive:
                marketplace = json.loads(
                    archive.read("yonsei-skills/.agents/plugins/marketplace.json")
                )
                self.assertEqual(
                    [item["name"] for item in marketplace["plugins"]],
                    list(MODULE.STUDENT_PLUGINS),
                )
                self.assertIn(
                    "yonsei-skills/plugins/yonsei-academic-copilot/"
                    "skills/calculate-yonsei-graduation-progress/SKILL.md",
                    archive.namelist(),
                )

    def test_skill_and_universal_plugin_contain_all_student_workflows(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.build(output)
            with zipfile.ZipFile(output / "yonsei-student-life.skill") as archive:
                skill_files = [
                    name for name in archive.namelist()
                    if name.endswith("/SKILL.md") and "/workflows/" in name
                ]
                self.assertEqual(len(skill_files), 35)
                self.assertIn("yonsei-student-life/SKILL.md", archive.namelist())
            with zipfile.ZipFile(output / "yonsei-universal-plugin.zip") as archive:
                manifest = json.loads(
                    archive.read("yonsei-student-life/.codex-plugin/plugin.json")
                )
                self.assertEqual(manifest["name"], "yonsei-student-life")
                self.assertEqual(manifest["version"], "9.8.7")
                skill_files = [
                    name for name in archive.namelist()
                    if name.endswith("/SKILL.md") and "/skills/" in name
                ]
                self.assertEqual(len(skill_files), 35)

    def test_packages_are_deterministic_and_checksums_match(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_output = Path(first)
            second_output = Path(second)
            self.build(first_output)
            self.build(second_output)
            for name in MODULE.ARCHIVES:
                self.assertEqual(
                    hashlib.sha256((first_output / name).read_bytes()).hexdigest(),
                    hashlib.sha256((second_output / name).read_bytes()).hexdigest(),
                )
            checksums = {
                name: digest
                for digest, name in (
                    line.split("  ", 1)
                    for line in (first_output / "SHA256SUMS.txt").read_text().splitlines()
                )
            }
            for name in MODULE.ARCHIVES:
                self.assertEqual(
                    checksums[name],
                    hashlib.sha256((first_output / name).read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
