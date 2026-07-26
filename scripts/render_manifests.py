#!/usr/bin/env python3
"""Render plugin manifests and both marketplaces from one specification."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/mrcha033/yonsei-skills"
AUTHOR = {"name": "mrcha033", "url": "https://github.com/mrcha033"}
OUTCOMES = json.loads(
    (ROOT / "contracts" / "skill-outcomes.json").read_text(encoding="utf-8")
)
INSTALLATIONS = {
    plugin["plugin"]: plugin["installation"]
    for plugin in OUTCOMES["plugins"]
}

SPECS = {
    "learnus-course-copilot": {
        "version": "0.3.0",
        "display": "LearnUs Course Tools",
        "description": "Manage a memory-only LearnUs session and separately list authorized courses, deadlines, or materials with fail-closed parsing.",
        "short": "Fine-grained LearnUs session and course tools",
        "long": "Install four result-specific skills for hidden-terminal session management, course discovery, assignment deadlines, and material links without persisting credentials.",
        "keywords": ["learnus", "yonsei", "lms", "course"],
        "capabilities": [
            "Memory-only LearnUs session management",
            "Authorized course listing",
            "Associated deadline reporting",
            "Material and video inventory",
        ],
        "prompts": [
            "List my authorized LearnUs courses.",
            "Show the deadlines in this LearnUs course.",
            "List the materials in this LearnUs course.",
        ],
    },
    "yonsei-certificate-assistant": {
        "version": "0.1.0",
        "display": "Yonsei Certificate Assistant",
        "description": "Choose and complete an official Yonsei electronic or paper certificate issuance path without bypassing print controls.",
        "short": "Issue valid Yonsei certificates on macOS",
        "long": "Choose the valid electronic-original or paper-original workflow, enter through the official portal, and avoid print-control bypasses that would produce an invalid copy.",
        "keywords": ["yonsei", "certificate", "pdf", "macos"],
        "capabilities": ["Certificate path selection", "Official issuance guidance", "Mac compatibility checks"],
        "prompts": ["Help me issue a valid Yonsei certificate from my Mac."],
    },
    "yonsei-notice-monitor": {
        "version": "0.2.0",
        "display": "Yonsei Notice Tools",
        "description": "Search official Yonsei notices, extract contextual deadline candidates, or detect changes against an explicit local snapshot.",
        "short": "Search notices, deadlines, and changes",
        "long": "Install three public read-only skills for globally sorted official notice search, contextual deadline extraction, and explicit-state change detection.",
        "keywords": ["yonsei", "notices", "it", "monitor"],
        "capabilities": [
            "Globally sorted official notice search",
            "Contextual deadline candidates",
            "Explicit-state change detection",
        ],
        "prompts": [
            "Search current official Yonsei notices.",
            "List upcoming deadlines from recent Yonsei notices.",
            "Show notices changed since my last snapshot.",
        ],
    },
    "yonsei-academic-copilot": {
        "version": "0.1.0",
        "display": "Yonsei Academic Copilot",
        "description": "Inspect authorized Yonsei academic information through the official academic system with a read-only first release.",
        "short": "Inspect authorized academic information safely",
        "long": "Reach the official academic information system, verify the authenticated scope, and summarize only the records explicitly requested by the user.",
        "keywords": ["yonsei", "academic", "records", "student"],
        "capabilities": ["Academic system diagnostics", "Authorized record inspection", "Read-only summaries"],
        "prompts": ["Inspect my authorized Yonsei academic information."],
    },
    "yonsei-course-registration": {
        "version": "0.2.0",
        "display": "Yonsei Course Planner",
        "description": "Normalize supplied Yonsei course rows, audit a selected plan, check schedule conflicts, build ranked timetables, or diagnose official entry access without registration writes.",
        "short": "Fine-grained read-only Yonsei course planning",
        "long": "Install five result-specific skills for course-data normalization, conflict checks, course-plan audits, deterministic timetable construction, and bounded entry-point diagnostics.",
        "keywords": ["yonsei", "courses", "registration", "schedule"],
        "capabilities": [
            "Course-row normalization",
            "Schedule and campus conflict checks",
            "Explicit course-plan constraint audits",
            "Ranked timetable construction",
            "Official entry diagnostics",
        ],
        "prompts": [
            "Normalize these Yonsei course rows.",
            "Audit this Yonsei course plan against my constraints.",
            "Check this proposed Yonsei timetable for conflicts.",
            "Build ranked conflict-free timetables from these choices.",
        ],
    },
    "yonsei-attendance-copilot": {
        "version": "0.1.0",
        "display": "Yonsei Attendance Copilot",
        "description": "Review the user's authorized Yonsei electronic attendance records without performing check-ins or location spoofing.",
        "short": "Review electronic attendance records safely",
        "long": "Reach the official electronic attendance system and summarize authorized records in a strictly read-only workflow.",
        "keywords": ["yonsei", "attendance", "rollbook", "student"],
        "capabilities": ["Attendance system diagnostics", "Authorized record review", "Read-only summaries"],
        "prompts": ["Review my authorized Yonsei attendance records."],
    },
    "yonsei-shuttle-booking": {
        "version": "0.1.0",
        "display": "Yonsei Shuttle Booking",
        "description": "Check Yonsei International Campus shuttle options and require explicit confirmation before a reservation is submitted.",
        "short": "Check shuttle seats and guard reservations",
        "long": "Use the official shuttle entry point, present exact route and time details, and stop for confirmation immediately before reservation submission.",
        "keywords": ["yonsei", "shuttle", "booking", "campus"],
        "capabilities": ["Shuttle entry diagnostics", "Trip option review", "Confirmation-gated booking"],
        "prompts": ["Find a Yonsei shuttle option and prepare a reservation."],
    },
    "yonsei-space-reservation": {
        "version": "0.1.0",
        "display": "Yonsei Space Reservation",
        "description": "Check Yonsei space availability and require explicit confirmation before sending a reservation request.",
        "short": "Check spaces and guard reservation requests",
        "long": "Use the official space reservation system, summarize constraints and availability, and stop for confirmation before submitting a request.",
        "keywords": ["yonsei", "space", "room", "reservation"],
        "capabilities": ["Space system diagnostics", "Availability review", "Confirmation-gated requests"],
        "prompts": ["Find an available Yonsei space and prepare a reservation request."],
    },
    "yonsei-yri": {
        "version": "0.1.0",
        "display": "Yonsei YRI",
        "description": "Open and inspect authorized Yonsei Researcher Information records with confirmation required for every write.",
        "short": "Inspect research achievement records safely",
        "long": "Use the official YRI endpoint, verify the user's authorized scope, summarize requested records, and present a field-level diff before any write.",
        "keywords": ["yonsei", "yri", "research", "achievements"],
        "capabilities": ["YRI access diagnostics", "Authorized record inspection", "Confirmation-gated writes"],
        "prompts": ["Inspect my authorized YRI research achievement records."],
    },
    "yonsei-rms": {
        "version": "0.1.0",
        "display": "Yonsei RMS",
        "description": "Open and inspect authorized Yonsei Research Management System records with confirmation required for every write.",
        "short": "Inspect research management records safely",
        "long": "Use the official RMS endpoint, limit inspection to the user's authorized scope, and require a field-level review before any submission or change.",
        "keywords": ["yonsei", "rms", "research", "management"],
        "capabilities": ["RMS access diagnostics", "Authorized record inspection", "Confirmation-gated writes"],
        "prompts": ["Inspect my authorized Yonsei RMS records."],
    },
    "yonsei-erp": {
        "version": "0.1.0",
        "display": "Yonsei ERP",
        "description": "Open and inspect authorized Yonsei ERP workflows with a read-only default and confirmation before any administrative write.",
        "short": "Use authorized ERP workflows safely",
        "long": "Use the official ERP SSO endpoint, minimize sensitive-data exposure, and require explicit confirmation before any write, approval, or submission.",
        "keywords": ["yonsei", "erp", "administration", "workflow"],
        "capabilities": ["ERP access diagnostics", "Read-only workflow inspection", "Confirmation-gated writes"],
        "prompts": ["Open and inspect an authorized Yonsei ERP workflow."],
    },
    "yonsei-groupware": {
        "version": "0.1.0",
        "display": "Yonsei Groupware",
        "description": "Open and inspect authorized Yonsei groupware while requiring explicit confirmation before sending, approving, or sharing.",
        "short": "Use authorized groupware workflows safely",
        "long": "Use the official groupware endpoint, keep messages and documents scoped to the request, and stop before any external communication or approval.",
        "keywords": ["yonsei", "groupware", "collaboration", "workflow"],
        "capabilities": ["Groupware access diagnostics", "Authorized content inspection", "Confirmation-gated actions"],
        "prompts": ["Open and inspect my authorized Yonsei groupware."],
    },
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def codex_manifest(name: str, spec: dict, version: str | None = None) -> dict:
    return {
        "name": name,
        "version": version or spec["version"],
        "description": spec["description"],
        "author": AUTHOR,
        "homepage": REPOSITORY,
        "repository": REPOSITORY,
        "keywords": spec["keywords"],
        "skills": "./skills/",
        "interface": {
            "displayName": spec["display"],
            "shortDescription": spec["short"],
            "longDescription": spec["long"],
            "developerName": "mrcha033",
            "category": "Education",
            "capabilities": spec["capabilities"],
            "websiteURL": REPOSITORY,
            "defaultPrompt": spec["prompts"],
        },
    }


def claude_manifest(name: str, spec: dict) -> dict:
    return {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": name,
        "displayName": spec["display"],
        "version": spec["version"],
        "description": spec["description"],
        "author": AUTHOR,
        "homepage": REPOSITORY,
        "repository": REPOSITORY,
        "keywords": spec["keywords"],
        "skills": "./skills/",
    }


def main() -> int:
    for name, spec in SPECS.items():
        plugin_root = ROOT / "plugins" / name
        codex_path = plugin_root / ".codex-plugin" / "plugin.json"
        codex_version = spec["version"]
        if codex_path.exists():
            current = json.loads(codex_path.read_text(encoding="utf-8")).get("version", "")
            if current.startswith(f"{spec['version']}+codex."):
                codex_version = current
        write_json(codex_path, codex_manifest(name, spec, codex_version))
        write_json(plugin_root / ".claude-plugin" / "plugin.json", claude_manifest(name, spec))

    claude_marketplace = {
        "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
        "name": "yonsei-skills",
        "description": "Independently installable, outcome-tested Yonsei University skills.",
        "owner": {"name": "mrcha033"},
        "plugins": [
            {
                "name": name,
                "displayName": spec["display"],
                "source": f"./plugins/{name}",
                "description": spec["description"],
                "version": spec["version"],
                "author": {"name": "mrcha033"},
                "homepage": REPOSITORY,
                "repository": REPOSITORY,
                "category": "education",
                "tags": spec["keywords"],
            }
            for name, spec in SPECS.items()
            if INSTALLATIONS[name] == "AVAILABLE"
        ],
    }
    codex_marketplace = {
        "name": "yonsei-skills",
        "interface": {"displayName": "Yonsei Skills"},
        "plugins": [
            {
                "name": name,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{name}",
                },
                "policy": {
                    "installation": INSTALLATIONS[name],
                    "authentication": "ON_INSTALL",
                },
                "category": "Education",
            }
            for name in SPECS
        ],
    }
    write_json(ROOT / ".claude-plugin" / "marketplace.json", claude_marketplace)
    write_json(ROOT / ".agents" / "plugins" / "marketplace.json", codex_marketplace)
    print(f"Rendered {len(SPECS)} plugin manifests and the Claude marketplace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
