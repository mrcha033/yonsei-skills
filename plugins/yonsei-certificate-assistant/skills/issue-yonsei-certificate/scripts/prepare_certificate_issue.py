#!/usr/bin/env python3
"""Validate an end-to-end Yonsei free-print certificate request."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any


ALLOWED_LANGUAGES = {"ko", "en"}
ALLOWED_RESULTS = {"reviewed_pdf", "physical_print"}
PLATFORM_ALIASES = {
    "darwin": "macos",
    "mac": "macos",
    "macos": "macos",
    "linux": "linux",
    "windows": "windows",
    "win32": "windows",
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-field", "Expected a non-empty string.", path)
    return value.strip()


def normalize_platform(value: str | None = None) -> str:
    detected = value or platform.system()
    return PLATFORM_ALIASES.get(detected.strip().casefold(), "unsupported")


def run(payload: Any, *, system: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be an object.")
    certificate_type = text(payload.get("certificate_type"), "$.certificate_type")
    language = text(payload.get("language", "ko"), "$.language").lower()
    if language not in ALLOWED_LANGUAGES:
        raise InputError("invalid-language", f"language must be one of {sorted(ALLOWED_LANGUAGES)}.", "$.language")
    copies = payload.get("copies", 1)
    if not isinstance(copies, int) or isinstance(copies, bool) or copies != 1:
        raise InputError(
            "single-copy-only",
            "The compatibility flow supports one document-number reservation and one copy per issuance.",
            "$.copies",
        )
    purpose = text(payload.get("purpose"), "$.purpose")
    desired_result = text(payload.get("desired_result", "reviewed_pdf"), "$.desired_result")
    if desired_result not in ALLOWED_RESULTS:
        raise InputError("invalid-result", f"desired_result must be one of {sorted(ALLOWED_RESULTS)}.", "$.desired_result")
    printer = payload.get("printer")
    if desired_result == "physical_print":
        printer = text(printer, "$.printer")
    elif printer not in (None, ""):
        raise InputError("unexpected-printer", "printer is only accepted for physical_print.", "$.printer")

    forbidden = {
        "student_name",
        "student_id",
        "birth_date",
        "document_number",
        "verification_number",
        "grade",
        "degree_date",
    }
    supplied_forbidden = sorted(key for key in forbidden if key in payload)
    if supplied_forbidden:
        raise InputError(
            "certificate-content-not-accepted",
            "Certificate identity and content fields must come only from the official issuance response.",
            f"$.{supplied_forbidden[0]}",
        )
    host_platform = normalize_platform(system)
    if host_platform == "unsupported":
        raise InputError(
            "unsupported-platform",
            "Certificate issuance supports Windows, macOS, and Linux.",
            "$.platform",
        )
    if desired_result == "reviewed_pdf":
        issuance_path = "local-reportx-compatible-virtual-pdf-print"
        next_step = "doctor-and-prepare-official-assets"
        result_scope = "free-print-pdf-virtual-print"
    elif host_platform == "windows":
        issuance_path = "official-windows-reportx-physical-print"
        next_step = "doctor-official-reportx-and-physical-printer-then-open-browser"
        result_scope = "free-print-physical-print"
    else:
        issuance_path = "local-reportx-compatible-pdf-then-physical-print"
        next_step = "doctor-prepare-assets-save-pdf-then-print-named-printer"
        result_scope = "free-print-pdf-then-physical-print"

    return {
        "schema": "yonsei-certificate-issue-plan/v1",
        "ready": True,
        "platform": host_platform,
        "issuance_path": issuance_path,
        "certificate_type": certificate_type,
        "language": language,
        "copies": copies,
        "purpose": purpose,
        "desired_result": desired_result,
        "printer": printer,
        "official_free_print_required": True,
        "print_target": (
            "named-physical-printer"
            if desired_result == "physical_print"
            else "pdf-virtual-printer"
        ),
        "document_number_reservation": "one-shot-after-confirmation",
        "certificate_content_source": "official-authorized-report-only",
        "paid_electronic_certificate": False,
        "result_scope": result_scope,
        "student_cli_required": False,
        "next_step": next_step,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    parser.add_argument(
        "--platform",
        choices=("windows", "macos", "linux"),
        help="Override platform detection for packaging checks.",
    )
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8"))
        output = run(payload, system=args.platform)
        code = 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        output = {
            "schema": "yonsei-certificate-issue-error/v1",
            "error": {
                "code": getattr(exc, "code", "invalid-input"),
                "message": str(exc),
                "path": getattr(exc, "path", "$"),
            },
        }
        code = 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
