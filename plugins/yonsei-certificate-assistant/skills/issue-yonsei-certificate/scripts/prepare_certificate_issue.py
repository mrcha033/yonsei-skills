#!/usr/bin/env python3
"""Validate an end-to-end Yonsei free-print certificate request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_LANGUAGES = {"ko", "en"}
ALLOWED_RESULTS = {"reviewed_pdf", "physical_print"}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-field", "Expected a non-empty string.", path)
    return value.strip()


def run(payload: Any) -> dict[str, Any]:
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
    return {
        "schema": "yonsei-certificate-issue-plan/v1",
        "ready": True,
        "certificate_type": certificate_type,
        "language": language,
        "copies": copies,
        "purpose": purpose,
        "desired_result": desired_result,
        "printer": printer,
        "official_free_print_required": True,
        "document_number_reservation": "one-shot-after-confirmation",
        "certificate_content_source": "official-authorized-report-only",
        "paid_electronic_certificate": False,
        "next_step": "doctor-and-prepare-official-assets",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8"))
        output = run(payload)
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
