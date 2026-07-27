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
        "version": "0.2.0",
        "display": "Yonsei Academic Snapshot Tools",
        "description": "Normalize supplied class and enrollment snapshots or calculate a conservative grade summary without live-system claims or academic writes.",
        "short": "Audit supplied academic records safely",
        "long": "Install separate snapshot-only skills for class-list normalization, conservative grade calculations, and enrollment-status checks with completeness and privacy guards.",
        "keywords": ["yonsei", "academic", "records", "student"],
        "capabilities": [
            "Supplied class snapshot normalization",
            "Conservative term grade summaries",
            "Enrollment and registration status checks",
        ],
        "prompts": [
            "Normalize this authorized Yonsei class snapshot.",
            "Summarize this supplied Yonsei grade snapshot.",
            "Check this supplied enrollment status.",
        ],
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
        "version": "0.2.0",
        "display": "Yonsei Attendance Review Tools",
        "description": "Summarize supplied attendance records, identify user-review discrepancies, or prepare an unsent correction draft without check-in or location inference.",
        "short": "Review supplied attendance records safely",
        "long": "Install three snapshot-only skills for attendance totals, conservative discrepancy review, and unsent correction drafting while check-in and record changes stay disabled.",
        "keywords": ["yonsei", "attendance", "rollbook", "student"],
        "capabilities": [
            "Supplied attendance summaries",
            "User-review discrepancy detection",
            "Unsent correction drafts",
        ],
        "prompts": [
            "Summarize this Yonsei attendance snapshot.",
            "Find records in this attendance snapshot that I should review.",
            "Draft but do not send an attendance correction request.",
        ],
    },
    "yonsei-shuttle-booking": {
        "version": "0.2.0",
        "display": "Yonsei Shuttle Review Tools",
        "description": "Diagnose the official shuttle client or filter supplied trip and seat snapshots without reserving, waitlisting, cancelling, or polling.",
        "short": "Review shuttle options and seat snapshots",
        "long": "Install separate skills for official entry diagnostics, trip filtering, and conservative seat or waitlist verdicts while every reservation write remains disabled.",
        "keywords": ["yonsei", "shuttle", "booking", "campus"],
        "capabilities": [
            "Official shuttle client diagnostics",
            "Supplied trip option filtering",
            "Conservative seat and waitlist status",
        ],
        "prompts": [
            "Diagnose the Yonsei shuttle entry.",
            "Filter these supplied shuttle options.",
            "Check the seat status in this supplied trip snapshot.",
        ],
    },
    "yonsei-space-reservation": {
        "version": "0.2.0",
        "display": "Yonsei Space Planning Tools",
        "description": "Filter supplied room snapshots, check a proposal against official public rules, or prepare an unsent reservation draft without submission.",
        "short": "Check space candidates, rules, and drafts",
        "long": "Install separate skills for snapshot filtering, evidence-linked rule checks, and unsent request preparation while availability claims, payment, approval, and submission stay disabled.",
        "keywords": ["yonsei", "space", "room", "reservation"],
        "capabilities": [
            "Supplied space snapshot filtering",
            "Official public booking-rule checks",
            "Unsent reservation drafts",
        ],
        "prompts": [
            "Filter this supplied Yonsei space snapshot.",
            "Check this proposed booking against Yonsei public rules.",
            "Prepare but do not submit a space request.",
        ],
    },
    "yonsei-yri": {
        "version": "0.2.0",
        "display": "Yonsei YRI Export Tools",
        "description": "Normalize an authorized YRI export, reconcile it with a supplied reference list, or prepare an unsaved field-level change draft.",
        "short": "Audit supplied YRI research achievements",
        "long": "Install separate export-only skills for achievement listing, conservative missing-record reconciliation, and unsaved field-level change preparation.",
        "keywords": ["yonsei", "yri", "research", "achievements"],
        "capabilities": [
            "Authorized YRI export normalization",
            "Missing and duplicate candidate review",
            "Unsaved field-level change drafts",
        ],
        "prompts": [
            "List the achievements in this YRI export.",
            "Compare my YRI export with this reference bibliography.",
            "Prepare but do not save this YRI field change.",
        ],
    },
    "yonsei-rms": {
        "version": "0.2.0",
        "display": "Yonsei RMS Snapshot Tools",
        "description": "Summarize supplied RMS project data and audit its budget arithmetic or participant roles and periods without uploads, approvals, or submissions.",
        "short": "Audit supplied RMS project snapshots",
        "long": "Install separate snapshot-only skills for project summaries, budget consistency checks, and participant-period validation against explicit supplied data.",
        "keywords": ["yonsei", "rms", "research", "management"],
        "capabilities": [
            "Supplied project summaries",
            "Budget arithmetic audits",
            "Participant role and period checks",
        ],
        "prompts": [
            "Summarize this supplied RMS project snapshot.",
            "Check this RMS budget snapshot for inconsistencies.",
            "Validate these RMS participant roles and periods.",
        ],
    },
    "yonsei-erp": {
        "version": "0.2.0",
        "display": "Yonsei ERP Snapshot Tools",
        "description": "Filter supplied ERP request and approval snapshots or audit payment lifecycle status without accessing payroll, approving, paying, or submitting.",
        "short": "Review supplied ERP workflow snapshots",
        "long": "Install separate snapshot-only skills for request status, approval inbox, and payment lifecycle review with strict field whitelists and no administrative writes.",
        "keywords": ["yonsei", "erp", "administration", "workflow"],
        "capabilities": [
            "Supplied request status lists",
            "Approval inbox triage",
            "Payment lifecycle audits",
        ],
        "prompts": [
            "List requests in this authorized ERP snapshot.",
            "Triage this supplied ERP approval inbox.",
            "Check payment status in this supplied ERP snapshot.",
        ],
    },
    "yonsei-groupware": {
        "version": "0.2.0",
        "display": "Yonsei Groupware Offline Tools",
        "description": "Triage supplied approval data, search an explicit authorized document export, or prepare an unsent message without approving, sending, or sharing.",
        "short": "Review supplied groupware exports safely",
        "long": "Install separate offline skills for approval inbox triage, local authorized-export search, and unsent message drafting with no external communication or workflow mutation.",
        "keywords": ["yonsei", "groupware", "collaboration", "workflow"],
        "capabilities": [
            "Supplied approval inbox triage",
            "Authorized export document search",
            "Unsent message drafts",
        ],
        "prompts": [
            "Triage this supplied groupware approval snapshot.",
            "Search this authorized local groupware export.",
            "Draft but do not send this groupware message.",
        ],
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
