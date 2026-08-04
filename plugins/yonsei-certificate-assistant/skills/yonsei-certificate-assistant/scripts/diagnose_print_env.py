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
CERTIFICATE_ENTRY = "https://portal.yonsei.ac.kr/ui/index.html"


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
    if system not in {"Windows", "Darwin", "Linux"}:
        return {
            "id": "unsupported-platform",
            "summary": "This certificate workflow supports Windows, macOS, and Linux.",
            "next_steps": ["Continue from a supported desktop operating system."],
        }
    label = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}[system]
    if reportx_listening:
        return {
            "id": "loopback-listener-present",
            "summary": (
                f"A loopback ReportX listener is already using the print port on {label}. "
                "For PDF output it must be the packaged local compatibility printer."
            ),
            "next_steps": [
                "Run python3 scripts/icert_print.py doctor to verify the packaged agent token.",
                (
                    "If that check says agent DOWN, close the native ReportX tray/service "
                    "before starting the local PDF printer; never run both on the same port."
                ),
                "Open portal → 인터넷증명서 → 인터넷즉시발급.",
                "Choose 프린터 출력 once after arming the local agent.",
            ],
        }
    return {
        "id": "start-local-agent",
        "summary": (
            f"{label} uses the packaged local ReportX-compatible printer for the "
            "official free-print /SSO handoff and PDF result."
        ),
        "next_steps": [
            "python3 scripts/icert_print.py prepare-assets",
            (
                "python3 scripts/icert_print.py agent --allow-fetch "
                "--reserve-document-number"
            ),
            "python3 scripts/icert_print.py open",
            "In icert choose 프린터 출력 only after arming the agent.",
            "Run python3 scripts/icert_print.py wait-job.",
        ],
    }


def diagnose(*, include_printers: bool = False) -> dict[str, Any]:
    """Return the fast PDF-path diagnosis.

    Physical-printer discovery is deliberately opt-in.  It can invoke a slow
    platform command and is irrelevant to the default compatibility-PDF path.
    """

    system = platform.system()
    ports = {str(port): port_open(port) for port in REPORTX_PORTS}
    printers = list_printers(system) if include_printers else []
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
            "entry": CERTIFICATE_ENTRY,
            "entry_path": "인터넷증명서 → 인터넷즉시발급",
            "scope": "free-print-only",
            "excludes": ["전자증명서발급"],
            "plugin_installer": PLUGIN_INSTALLER,
        },
        "reportx": {
            "ports": ports,
            "listening": reportx_listening,
            "native_supported_os": system == "Windows",
            "compatibility_supported_os": system in {"Windows", "Darwin", "Linux"},
        },
        "printers": {
            "checked": include_printers,
            "all": printers,
            **classified,
            "lpstat_available": shutil.which("lpstat") is not None,
        },
        "recommendation": recommendation,
        "notes": [
            "Yonsei documents the official print path around the Windows ReportX component.",
            "The local Windows/macOS/Linux compatibility agent independently renders the returned prepared FP3 pages as a PDF.",
            "Native Windows ReportX remains available only for an explicitly requested physical printer.",
            "Document-number reservation requires explicit opt-in and is never automatically retried.",
            "이메일 전송 grants print rights, not a PDF attachment.",
            "A PDF container is not automatically an official electronic certificate or paper original.",
        ],
    }


def configure_utf8_stdio() -> None:
    """Keep Korean diagnostic output lossless on every desktop OS."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON (default).")
    parser.add_argument(
        "--text",
        action="store_true",
        help="Emit a short human-readable summary instead of JSON.",
    )
    parser.add_argument(
        "--include-printers",
        action="store_true",
        help="Also enumerate physical printers (not needed for PDF issuance).",
    )
    args = parser.parse_args()
    payload = diagnose(include_printers=args.include_printers)
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
