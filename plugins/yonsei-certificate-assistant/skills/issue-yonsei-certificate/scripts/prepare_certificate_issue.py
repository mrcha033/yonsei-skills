#!/usr/bin/env python3
"""Validate an end-to-end Yonsei free-print certificate request."""

from __future__ import annotations

import argparse
import decimal
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED_LANGUAGES = {"ko", "en"}
ALLOWED_RESULTS = {"reviewed_pdf", "physical_print"}
ALLOWED_LOGIN_STATES = {"connected", "login_required", "unknown"}
SUPPORTED_CONVERSION_SCALES = {"4.5"}
CERTIFICATE_TYPES = {
    "enrollment": "재학증명서",
    "transcript": "성적증명서",
    "graduation": "졸업증명서",
    "expected_graduation": "졸업예정증명서",
    "leave": "휴학증명서",
    "completion": "수료증명서",
}
CERTIFICATE_TYPE_ALIASES = {
    **{key: key for key in CERTIFICATE_TYPES},
    **{label: key for key, label in CERTIFICATE_TYPES.items()},
}
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


def boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise InputError("invalid-boolean", "Expected true or false.", path)
    return value


def certificate_type(value: Any) -> tuple[str, str]:
    supplied = text(value, "$.certificate_type")
    key = CERTIFICATE_TYPE_ALIASES.get(supplied)
    if key is None:
        raise InputError(
            "unsupported-certificate-type",
            "certificate_type must be one of "
            + ", ".join(CERTIFICATE_TYPES),
            "$.certificate_type",
        )
    return key, CERTIFICATE_TYPES[key]


def conversion_scale(value: Any, path: str) -> str:
    supplied = text(str(value) if isinstance(value, (int, float)) else value, path)
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", supplied):
        raise InputError(
            "invalid-conversion-scale",
            "conversion_scale must be a positive numeric scale such as 4.5.",
            path,
        )
    try:
        numeric = decimal.Decimal(supplied)
    except decimal.InvalidOperation as error:
        raise InputError("invalid-conversion-scale", "Invalid numeric scale.", path) from error
    if numeric <= 0 or numeric > 100:
        raise InputError(
            "invalid-conversion-scale",
            "conversion_scale must be greater than 0 and no more than 100.",
            path,
        )
    normalized = format(numeric.normalize(), "f")
    if normalized not in SUPPORTED_CONVERSION_SCALES:
        raise InputError(
            "unsupported-conversion-scale",
            "The current verified portal hot path supports conversion_scale 4.5 only.",
            path,
        )
    return normalized


def normalize_platform(value: str | None = None) -> str:
    detected = value or platform.system()
    return PLATFORM_ALIASES.get(detected.strip().casefold(), "unsupported")


def run(payload: Any, *, system: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be an object.")
    certificate_key, certificate_label = certificate_type(payload.get("certificate_type"))
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
    purpose_value = payload.get("purpose")
    purpose = None if purpose_value in (None, "") else text(purpose_value, "$.purpose")
    output_value = payload.get("output", payload.get("desired_result", "reviewed_pdf"))
    output_aliases = {
        "pdf": "reviewed_pdf",
        "reviewed_pdf": "reviewed_pdf",
        "physical_print": "physical_print",
        "print": "physical_print",
    }
    supplied_output = text(output_value, "$.output")
    desired_result = output_aliases.get(supplied_output, supplied_output)
    if desired_result not in ALLOWED_RESULTS:
        raise InputError(
            "invalid-result",
            "output must be pdf or physical_print.",
            "$.output",
        )
    printer = payload.get("printer")
    if desired_result == "physical_print":
        printer = text(printer, "$.printer")
    elif printer not in (None, ""):
        raise InputError("unexpected-printer", "printer is only accepted for physical_print.", "$.printer")

    login_state = text(payload.get("login_state", "unknown"), "$.login_state").lower()
    if login_state not in ALLOWED_LOGIN_STATES:
        raise InputError(
            "invalid-login-state",
            f"login_state must be one of {sorted(ALLOWED_LOGIN_STATES)}.",
            "$.login_state",
        )

    missing_user_fields: list[str] = []
    transcript = certificate_key == "transcript"
    if transcript:
        if "include_rank" not in payload:
            include_rank = None
            missing_user_fields.append("include_rank")
        else:
            include_rank = boolean(payload.get("include_rank"), "$.include_rank")
        if "include_conversion" not in payload:
            include_conversion = None
            missing_user_fields.append("include_conversion")
        else:
            include_conversion = boolean(
                payload.get("include_conversion"),
                "$.include_conversion",
            )
    else:
        include_rank = boolean(payload.get("include_rank", False), "$.include_rank")
        include_conversion = boolean(
            payload.get("include_conversion", False),
            "$.include_conversion",
        )
        if include_rank or include_conversion:
            raise InputError(
                "transcript-option-only",
                "Rank and GPA conversion options are only valid for a transcript.",
                "$.include_rank" if include_rank else "$.include_conversion",
            )
    raw_scale = payload.get("conversion_scale")
    if include_conversion is True:
        if raw_scale in (None, ""):
            scale = None
            missing_user_fields.append("conversion_scale")
        else:
            scale = conversion_scale(raw_scale, "$.conversion_scale")
    elif raw_scale not in (None, ""):
        raise InputError(
            "unexpected-conversion-scale",
            "conversion_scale is only accepted when include_conversion is true.",
            "$.conversion_scale",
        )
    else:
        scale = None

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
        next_step = "one-confirmed-issue-command-after-prewarm"
        result_scope = "free-print-pdf-virtual-print"
    elif host_platform == "windows":
        issuance_path = "official-windows-reportx-physical-print"
        next_step = "computer-use-native-windows-physical-route-after-one-review"
        result_scope = "free-print-physical-print"
    else:
        issuance_path = "local-reportx-compatible-pdf-then-physical-print"
        next_step = "one-confirmed-issue-command-after-prewarm"
        result_scope = "free-print-pdf-then-physical-print"

    review = {
        "certificate_type": certificate_key,
        "certificate_label": certificate_label,
        "language": language,
        "copies": copies,
        "output": "pdf" if desired_result == "reviewed_pdf" else "physical_print",
        "printer": printer,
        "include_rank": include_rank,
        "include_conversion": include_conversion,
        "conversion_scale": scale,
        "purpose": purpose,
        "login_state": login_state,
    }
    ready = login_state == "connected" and not missing_user_fields
    return {
        "schema": "yonsei-certificate-issue-plan/v2",
        "ready": ready,
        "platform": host_platform,
        "issuance_path": issuance_path,
        "certificate_type": certificate_key,
        "certificate_label": certificate_label,
        "language": language,
        "copies": copies,
        "purpose": purpose,
        "include_rank": include_rank,
        "include_conversion": include_conversion,
        "conversion_scale": scale,
        "login_state": login_state,
        "desired_result": desired_result,
        "output": review["output"],
        "printer": printer,
        "review": review,
        "authorization_required": True,
        "explicit_complete_issuance_request_counts_as_authorization": True,
        "authorization_prompt": (
            "Capture authorization in the initial intake unless the fully specified "
            "prompt already commands issuance; validate this review internally and "
            "run issue --confirm without asking for a second reply."
        ),
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
        "missing_user_fields": missing_user_fields,
        "runtime_checks": {
            "login_state": login_state,
            "detected_by": "visible-page inspection through Codex Computer Use",
            "user_supplied": False,
        },
        "next_step": (
            next_step
            if ready
            else (
                "collect-all-missing-user-fields-in-one-batch"
                if missing_user_fields
                else "complete-login-on-the-open-official-page-once"
            )
        ),
        "computer_use_request": {
            "certificate_label": certificate_label,
            "language_label": "영문" if language == "en" else "국문",
            "copies": copies,
            "rank": (
                "include"
                if include_rank is True
                else ("exclude" if include_rank is False else "missing")
            ),
            "conversion": (
                {"include": True, "scale": scale}
                if include_conversion is True
                else (
                    {"include": False, "scale": None}
                    if include_conversion is False
                    else {"include": None, "scale": None}
                )
            ),
            "output_action": "프린터 출력",
        },
    }


def configure_utf8_stdio() -> None:
    """Keep Korean JSON input and output lossless on every desktop OS."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
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
