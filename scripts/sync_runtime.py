#!/usr/bin/env python3
"""Vendor the shared service runtime into independently installable plugins."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "yonsei-service-runtime"
PLUGIN_SERVICES = {
    "yonsei-certificate-assistant": ["certificate"],
    "yonsei-notice-monitor": ["university-notices", "it-notices"],
    "yonsei-academic-copilot": ["academic"],
    "yonsei-course-registration": [
        "course-undergraduate",
        "course-graduate",
        "course-catalog",
    ],
    "yonsei-attendance-copilot": ["attendance"],
    "yonsei-shuttle-booking": ["shuttle"],
    "yonsei-space-reservation": ["space"],
    "yonsei-yri": ["yri"],
    "yonsei-rms": ["rms"],
    "yonsei-erp": ["erp"],
    "yonsei-groupware": ["groupware"],
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync_plugin(plugin_name: str, catalog: dict, *, check: bool) -> list[str]:
    skill_root = ROOT / "plugins" / plugin_name / "skills" / plugin_name
    script_target = skill_root / "scripts" / "yonsei_service.py"
    catalog_target = skill_root / "references" / "services.json"
    selected = {
        service_id: catalog["services"][service_id]
        for service_id in PLUGIN_SERVICES[plugin_name]
    }
    subset = {
        "schema": catalog["schema"],
        "updated_at": catalog["updated_at"],
        "sources": catalog["sources"],
        "services": selected,
    }
    rendered = json.dumps(subset, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    problems: list[str] = []
    if check:
        if not script_target.exists() or digest(script_target) != digest(PACKAGE / "yonsei_service.py"):
            problems.append(f"{plugin_name}: vendored runtime is stale")
        if not catalog_target.exists() or catalog_target.read_text(encoding="utf-8") != rendered:
            problems.append(f"{plugin_name}: vendored catalog is stale")
        return problems
    script_target.parent.mkdir(parents=True, exist_ok=True)
    catalog_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PACKAGE / "yonsei_service.py", script_target)
    script_target.chmod(0o755)
    catalog_target.write_text(rendered, encoding="utf-8")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalog = json.loads((PACKAGE / "services.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    for plugin_name in PLUGIN_SERVICES:
        problems.extend(sync_plugin(plugin_name, catalog, check=args.check))
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print(
        "Runtime distributions are current."
        if args.check
        else f"Synced runtime into {len(PLUGIN_SERVICES)} independent plugins."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
