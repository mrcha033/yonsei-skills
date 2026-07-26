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
OUTCOMES = ROOT / "contracts" / "skill-outcomes.json"
PLUGIN_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_NAME = re.compile(r"^name:\s*([a-z0-9]+(?:-[a-z0-9]+)*)\s*$", re.MULTILINE)


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def main() -> int:
    problems: list[str] = []
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES.read_text(encoding="utf-8"))
    outcome_plugins = {
        item["plugin"]: item
        for item in outcomes["plugins"]
    }
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
    if set(names) != set(outcome_plugins):
        fail(problems, "marketplace and outcome-contract plugin sets must match")
    if "/Users/" in (ROOT / "README.md").read_text(encoding="utf-8"):
        fail(problems, "README must not contain a developer-specific absolute path")

    for entry in entries:
        name = entry.get("name", "")
        if not PLUGIN_NAME.fullmatch(name):
            fail(problems, f"invalid plugin name: {name!r}")
            continue
        plugin_root = ROOT / "plugins" / name
        manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
        if not manifest_path.is_file():
            fail(problems, f"{name}: missing Codex manifest")
            continue
        skill_paths = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != name:
            fail(problems, f"{name}: manifest name mismatch")
        contract = outcome_plugins.get(name, {})
        declared = {
            outcome["skill"]
            for outcome in contract.get("outcomes", [])
            if outcome["state"] in {"implementation", "implemented"}
        }
        packaged: set[str] = set()
        for skill_path in skill_paths:
            skill_name = skill_path.parent.name
            packaged.add(skill_name)
            skill_text = skill_path.read_text(encoding="utf-8")
            match = FRONTMATTER_NAME.search(skill_text)
            if match is None or match.group(1) != skill_name:
                fail(problems, f"{name}/{skill_name}: frontmatter name mismatch")
            if not (skill_path.parent / "agents" / "openai.yaml").is_file():
                fail(problems, f"{name}/{skill_name}: missing agents/openai.yaml")
            if "[TODO:" in skill_text:
                fail(problems, f"{name}/{skill_name}: unresolved skill TODO")
            if "/Users/" in skill_text or "../plugins/" in skill_text:
                fail(problems, f"{name}/{skill_name}: non-portable path dependency")
            if "yonsei-portal-copilot" in skill_text:
                fail(problems, f"{name}/{skill_name}: cross-plugin runtime dependency detected")
            if name != "learnus-course-copilot" and "secuway connect" in skill_text.lower():
                fail(problems, f"{name}/{skill_name}: direct Secuway connection dependency detected")
        if contract.get("release") != "external-user-work":
            if packaged != declared:
                fail(
                    problems,
                    f"{name}: packaged skills {sorted(packaged)} do not match "
                    f"declared implementation skills {sorted(declared)}",
                )
        installation = entry.get("policy", {}).get("installation")
        expected_installation = contract.get("installation")
        if expected_installation not in {"AVAILABLE", "NOT_AVAILABLE"}:
            fail(problems, f"{name}: contract has invalid installation policy")
            continue
        if installation != expected_installation:
            fail(
                problems,
                f"{name}: installation policy must be {expected_installation}",
            )

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
    published = sum(
        entry.get("policy", {}).get("installation") == "AVAILABLE"
        for entry in entries
    )
    print(
        f"Validated {len(entries)} marketplace entries; "
        f"{published} are available for installation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
