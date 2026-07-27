#!/usr/bin/env python3
"""Check a user-supplied Yonsei enrollment-status snapshot."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-academic-enrollment-status/v1"
ERROR_SCHEMA = "yonsei-academic-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password",
    "passwd",
    "userpw",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "cookies",
    "session",
    "sessionid",
}
STATUS_ALIASES = {
    "재학": "enrolled",
    "enrolled": "enrolled",
    "active": "enrolled",
    "휴학": "leave",
    "휴학중": "leave",
    "leave": "leave",
    "leave-of-absence": "leave",
    "수료": "completed",
    "completed": "completed",
    "졸업": "graduated",
    "graduated": "graduated",
    "제적": "withdrawn",
    "퇴학": "withdrawn",
    "withdrawn": "withdrawn",
}
FIELD_ALIASES = {
    "status": ("status", "student_status", "학적상태", "재학구분"),
    "registered_for_term": (
        "registered_for_term",
        "term_registered",
        "등록여부",
        "학기등록여부",
    ),
    "program": ("program", "degree_program", "과정"),
    "college": ("college", "대학", "소속대학"),
    "major": ("major", "전공", "소속전공"),
    "year_level": ("year_level", "year", "학년"),
    "expected_graduation": ("expected_graduation", "졸업예정", "졸업예정일"),
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_credentials(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "credential-field-not-allowed",
                    "Credential or session fields are not accepted.",
                    f"{path}.{key}",
                )
            scan_credentials(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_credentials(item, f"{path}[{index}]")


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "A non-empty text value is required.", path)
    return value.strip()


def first(row: dict[str, Any], field: str) -> Any:
    for key in FIELD_ALIASES[field]:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def optional_text(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise InputError("invalid-text", "Expected text.", path)
    return value.strip() or None


def optional_year_level(value: Any, path: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise InputError("invalid-year-level", "Year level must be an integer.", path)
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise InputError("invalid-year-level", "Year level must be an integer.", path) from error
    if not math.isfinite(number) or int(number) != number or not 1 <= number <= 20:
        raise InputError("invalid-year-level", "Year level is out of range.", path)
    return int(number)


def normalize_registered(value: Any, path: str) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    key = str(value).strip().lower()
    if key in {"yes", "y", "true", "registered", "등록", "등록완료"}:
        return True
    if key in {"no", "n", "false", "not-registered", "미등록", "미등록상태"}:
        return False
    raise InputError(
        "unknown-registration-state",
        "Term-registration state is not recognized.",
        path,
    )


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be a JSON object.")
    scan_credentials(payload)
    captured_at = required_text(payload.get("captured_at"), "$.captured_at")
    term = required_text(payload.get("term"), "$.term")
    enrollment = payload.get("enrollment")
    if not isinstance(enrollment, dict):
        raise InputError(
            "invalid-enrollment",
            "Input must contain an enrollment object.",
            "$.enrollment",
        )
    raw_status = required_text(first(enrollment, "status"), "$.enrollment.status")
    status_key = raw_status.lower()
    if status_key not in STATUS_ALIASES:
        raise InputError(
            "unknown-academic-status",
            "Academic status is not recognized.",
            "$.enrollment.status",
        )
    status = STATUS_ALIASES[status_key]
    registered = normalize_registered(
        first(enrollment, "registered_for_term"),
        "$.enrollment.registered_for_term",
    )
    normalized = {
        "status": status,
        "status_displayed": raw_status,
        "registered_for_term": registered,
        "program": optional_text(first(enrollment, "program"), "$.enrollment.program"),
        "college": optional_text(first(enrollment, "college"), "$.enrollment.college"),
        "major": optional_text(first(enrollment, "major"), "$.enrollment.major"),
        "year_level": optional_year_level(
            first(enrollment, "year_level"), "$.enrollment.year_level"
        ),
        "expected_graduation": optional_text(
            first(enrollment, "expected_graduation"),
            "$.enrollment.expected_graduation",
        ),
    }
    unknowns: list[dict[str, str]] = []
    if registered is None:
        unknowns.append(
            {
                "field": "registered_for_term",
                "reason": "The snapshot does not state current-term registration.",
            }
        )
    contradictions: list[dict[str, str]] = []
    if registered is True and status in {"leave", "graduated", "withdrawn"}:
        contradictions.append(
            {
                "type": "status-registration-conflict",
                "message": (
                    "The snapshot says registered_for_term=true while the displayed "
                    f"academic status is {status}."
                ),
            }
        )
    return {
        "schema": OUTPUT_SCHEMA,
        "ok": True,
        "term": term,
        "enrollment": normalized,
        "complete": not unknowns and not contradictions,
        "unknowns": unknowns,
        "contradictions": contradictions,
        "interpretation": {
            "snapshot_status_normalized": True,
            "service_eligibility_inferred": False,
            "graduation_eligibility_inferred": False,
        },
        "provenance": {
            "mode": "user-supplied-snapshot",
            "captured_at": captured_at,
            "live_system_queried": False,
        },
    }


def load_input(path: str) -> Any:
    try:
        if path == "-":
            return json.load(sys.stdin, parse_constant=reject_json_constant)
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=reject_json_constant,
        )
    except InputError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise InputError("invalid-json", "Could not read JSON input.") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="JSON file, or - for stdin")
    args = parser.parse_args()
    try:
        output = run(load_input(args.input))
        exit_code = 0
    except InputError as error:
        output = {
            "schema": ERROR_SCHEMA,
            "ok": False,
            "error": {"code": error.code, "message": str(error), "path": error.path},
        }
        exit_code = 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
