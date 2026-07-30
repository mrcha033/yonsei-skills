#!/usr/bin/env python3
"""Diagnose the local environment for official or clean-room ReportX paths.

Does not install software, open the portal, accept credentials, or claim that
a saved response is an official certificate.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import subprocess
import sys
from typing import Any


REPORTX_PORTS = (65432, 65433)
PLUGIN_INSTALLER = (
    "https://icert.yonsei.ac.kr/ys1.0/module/ICT_REPORTX_SETUP.exe"
)
ICERT_HOME = "https://icert.yonsei.ac.kr/"


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_text(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (completed.stdout or "") + (completed.stderr or "")


def list_printers(system: str) -> list[str]:
    names: list[str] = []
    if system == "Darwin":
        text = run_text(["lpstat", "-a"])
        for line in text.splitlines():
            part = line.split(" ", 1)[0].strip()
            if part:
                names.append(part)
        return names
    if system == "Windows":
        text = run_text(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Printer | Select-Object -ExpandProperty Name",
            ]
        )
        for line in text.splitlines():
            name = line.strip()
            if name:
                names.append(name)
        return names
    # Linux / other
    text = run_text(["lpstat", "-a"])
    for line in text.splitlines():
        part = line.split(" ", 1)[0].strip()
        if part:
            names.append(part)
    return names


def classify_printers(names: list[str]) -> dict[str, list[str]]:
    virtual_hints = (
        "pdf",
        "xps",
        "onenote",
        "fax",
        "document writer",
        "print to",
        "cups-pdf",
        "modu",
        "모두의",
        "bullzip",
        "cutePDF",
        "dopdf",
        "nitro",
        "foxit",
        "adobe pdf",
    )
    physical: list[str] = []
    virtual: list[str] = []
    for name in names:
        lower = name.lower()
        if any(hint in lower for hint in virtual_hints):
            virtual.append(name)
        else:
            physical.append(name)
    return {"physical_candidates": physical, "virtual_candidates": virtual}


def recommended_path(
    *,
    system: str,
    reportx_listening: bool,
    physical: list[str],
    virtual: list[str],
) -> dict[str, Any]:
    if system != "Windows":
        label = "macOS" if system == "Darwin" else "Linux"
        if system not in {"Darwin", "Linux"}:
            return {
                "id": "unsupported-platform",
                "summary": (
                    "This certificate workflow supports Windows, macOS, and Linux."
                ),
                "next_steps": [
                    "Continue from a supported desktop operating system.",
                ],
            }
        if reportx_listening:
            return {
                "id": "local-agent-up",
                "summary": (
                    f"A loopback ReportX listener is already running on {label}. The "
                    "clean-room agent needs no DevTools bridge or page capture."
                ),
                "next_steps": [
                    "Keep the agent foreground process running.",
                    "Open portal → 인터넷증명서 → 인터넷즉시발급",
                    "Choose 프린터 출력; the official iframe sends /SSO automatically.",
                    "Run python3 scripts/icert_print.py wait-job, then inspect the exact status.",
                ],
            }
        return {
            "id": "start-local-agent",
            "summary": (
                f"{label} uses the packaged clean-room listener for the normal "
                "/SSO handoff and an unverified compatibility PDF."
            ),
            "next_steps": [
                "python3 scripts/icert_print.py prepare-assets",
                (
                    "python3 scripts/icert_print.py agent --allow-fetch "
                    "--reserve-document-number"
                ),
                "python3 scripts/icert_print.py open",
                "In icert choose 프린터 출력 only.",
                "Run python3 scripts/icert_print.py wait-job.",
            ],
        }
    if not reportx_listening:
        return {
            "id": "install-reportx",
            "summary": "Windows host detected, but ReportX is not listening on 65432/65433.",
            "next_steps": [
                f"Install or relaunch ICT ReportX: {PLUGIN_INSTALLER}",
                "Or run the clean-room listener only for interoperability testing.",
                "Re-open the browser on icert and allow the plugin prompt.",
                "Re-run this diagnostic until a ReportX port is open.",
            ],
        }
    if physical:
        return {
            "id": "physical-print",
            "summary": "ReportX appears up and at least one non-virtual printer is visible.",
            "next_steps": [
                "In icert choose 프린터 출력 and select the physical printer.",
                "If the site rejects the device, try another real printer or a campus kiosk.",
            ],
            "preferred_printers": physical[:5],
        }
    if virtual:
        return {
            "id": "virtual-pdf",
            "summary": "ReportX appears up; only virtual/PDF-like printers were classified.",
            "next_steps": [
                "In icert choose 프린터 출력 and select the virtual PDF printer.",
                "Save the PDF only to a path the user names; call it a print capture, not a paper original.",
                "If rejected, install a certificate-oriented virtual printer or attach a physical printer.",
            ],
            "preferred_printers": virtual[:5],
        }
    return {
        "id": "add-printer",
        "summary": "ReportX appears up, but no printers were found.",
        "next_steps": [
            "Add a physical printer for paper originals, or install a virtual PDF printer for file capture.",
            "Confirm Windows sees the device before returning to icert.",
        ],
    }


def diagnose() -> dict[str, Any]:
    system = platform.system()
    ports = {str(port): port_open(port) for port in REPORTX_PORTS}
    printers = list_printers(system)
    classified = classify_printers(printers)
    reportx_listening = any(ports.values())
    recommendation = recommended_path(
        system=system,
        reportx_listening=reportx_listening,
        physical=classified["physical_candidates"],
        virtual=classified["virtual_candidates"],
    )
    return {
        "ok": True,
        "platform": {
            "system": system,
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "icert": {
            "home": ICERT_HOME,
            "scope": "free-print-only",
            "excludes": ["전자증명서발급"],
            "plugin_installer": PLUGIN_INSTALLER,
        },
        "reportx": {
            "ports": ports,
            "listening": reportx_listening,
            "native_supported_os": system == "Windows",
            "compatibility_supported_os": system in {"Darwin", "Linux"},
        },
        "printers": {
            "all": printers,
            **classified,
            "lpstat_available": shutil.which("lpstat") is not None,
        },
        "recommendation": recommendation,
        "notes": [
            "Yonsei documents the official print path around the Windows ReportX component.",
            "The clean-room macOS/Linux agent independently renders the returned prepared FP3 pages as an unverified compatibility PDF.",
            "Document-number reservation requires explicit opt-in and is never automatically retried.",
            "이메일 전송 grants print rights, not a PDF attachment.",
            "A PDF container is not automatically an official electronic certificate or paper original.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON (default).")
    parser.add_argument(
        "--text",
        action="store_true",
        help="Emit a short human-readable summary instead of JSON.",
    )
    args = parser.parse_args()
    payload = diagnose()
    if args.text and not args.json:
        rec = payload["recommendation"]
        print(f"platform: {payload['platform']['system']}")
        print(f"reportx_listening: {payload['reportx']['listening']}")
        print(f"printers: {len(payload['printers']['all'])}")
        print(f"path: {rec['id']}")
        print(rec["summary"])
        for step in rec.get("next_steps", []):
            print(f"- {step}")
        return 0
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
