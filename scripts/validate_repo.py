#!/usr/bin/env python3
"""Repository-level structural and independence checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
PLUGIN_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def main() -> int:
    problems: list[str] = []
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    if marketplace.get("name") != "yonsei-skills":
        fail(problems, "marketplace name must be yonsei-skills")
    entries = marketplace.get("plugins", [])
    names = [entry.get("name") for entry in entries]
    if len(names) != len(set(names)):
        fail(problems, "marketplace plugin names must be unique")
    if "yonsei-portal-copilot" in names:
        fail(problems, "yonsei-portal-copilot must not be a required marketplace entry")
    if "yonsei-vpn" in names:
        fail(problems, "yonsei-vpn must remain unpublished while Secuway is under repair")

    for entry in entries:
        name = entry.get("name", "")
        if not PLUGIN_NAME.fullmatch(name):
            fail(problems, f"invalid plugin name: {name!r}")
            continue
        plugin_root = ROOT / "plugins" / name
        manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
        skill_path = plugin_root / "skills" / name / "SKILL.md"
        if not manifest_path.is_file():
            fail(problems, f"{name}: missing Codex manifest")
            continue
        if not skill_path.is_file():
            fail(problems, f"{name}: missing matching skill")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != name:
            fail(problems, f"{name}: manifest name mismatch")
        skill_text = skill_path.read_text(encoding="utf-8")
        if "[TODO:" in skill_text:
            fail(problems, f"{name}: unresolved skill TODO")
        if "../plugins/" in skill_text or "yonsei-portal-copilot" in skill_text:
            fail(problems, f"{name}: cross-plugin runtime dependency detected")
        if name != "learnus-course-copilot" and "secuway connect" in skill_text.lower():
            fail(problems, f"{name}: direct Secuway connection dependency detected")

    sync = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_runtime.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if sync.returncode:
        fail(problems, sync.stdout.strip() or sync.stderr.strip())

    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        return 1
    print(f"Validated {len(entries)} independently installable plugins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
