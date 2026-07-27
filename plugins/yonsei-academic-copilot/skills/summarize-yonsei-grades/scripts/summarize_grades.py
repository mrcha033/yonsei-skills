#!/usr/bin/env python3
"""Summarize one user-supplied Yonsei term-grade snapshot."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-academic-grade-summary/v1"
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
GRADE_POINTS = {
    "A+": 4.3,
    "A0": 4.0,
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B0": 3.0,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C0": 2.0,
    "C": 2.0,
    "C-": 1.7,
    "D+": 1.3,
    "D0": 1.0,
    "D": 1.0,
    "D-": 0.7,
    "F": 0.0,
}
PASS_GRADES = {"P", "S"}
FAIL_NO_GPA_GRADES = {"NP", "U"}
EXCLUDED_GRADES = {"W"}
PENDING_GRADES = {"I"}
KEYS = {
    "course_code": ("course_code", "courseCode", "code", "학정번호", "교과목번호"),
    "section": ("section", "class_number", "분반"),
    "title": ("title", "course_name", "name", "교과목명"),
    "credits": ("credits", "credit", "학점"),
    "grade": ("grade", "letter_grade", "성적", "등급"),
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
    for key in KEYS[field]:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def finite_number(value: Any, path: str, *, non_negative: bool = True) -> float:
    if isinstance(value, bool):
        raise InputError("invalid-number", "A numeric value is required.", path)
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise InputError("invalid-number", "A numeric value is required.", path) from error
    if not math.isfinite(result) or (non_negative and result < 0):
        raise InputError("invalid-number", "Number must be finite and non-negative.", path)
    return result


def normalize_grade(value: Any, path: str) -> str:
    grade = required_text(value, path).upper().replace(" ", "")
    recognized = (
        set(GRADE_POINTS)
        | PASS_GRADES
        | FAIL_NO_GPA_GRADES
        | EXCLUDED_GRADES
        | PENDING_GRADES
    )
    if grade not in recognized:
        raise InputError("unknown-grade", "Grade is not in the packaged grade scale.", path)
    return grade


def normalize_row(row: Any, index: int) -> dict[str, Any]:
    path = f"$.grades[{index}]"
    if not isinstance(row, dict):
        raise InputError("invalid-grade-row", "Each grade row must be an object.", path)
    code = required_text(first(row, "course_code"), f"{path}.course_code").upper()
    title = required_text(first(row, "title"), f"{path}.title")
    section_value = first(row, "section")
    section = str(section_value).strip() if section_value not in (None, "") else None
    credits = finite_number(first(row, "credits"), f"{path}.credits")
    grade = normalize_grade(first(row, "grade"), f"{path}.grade")
    points = GRADE_POINTS.get(grade)
    included_in_gpa = points is not None
    earned = (
        credits
        if (included_in_gpa and grade != "F") or grade in PASS_GRADES
        else 0.0
    )
    return {
        "id": f"{code}-{section}" if section else code,
        "course_code": code,
        "section": section,
        "title": title,
        "credits": credits,
        "grade": grade,
        "grade_points": points,
        "included_in_gpa": included_in_gpa,
        "earned_credits": earned,
        "pending": grade in PENDING_GRADES,
        "excluded_reason": (
            "pass-fail"
            if grade in PASS_GRADES | FAIL_NO_GPA_GRADES
            else "withdrawn"
            if grade in EXCLUDED_GRADES
            else "pending"
            if grade in PENDING_GRADES
            else None
        ),
    }


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be a JSON object.")
    scan_credentials(payload)
    captured_at = required_text(payload.get("captured_at"), "$.captured_at")
    term = required_text(payload.get("term"), "$.term")
    rows = payload.get("grades")
    if not isinstance(rows, list):
        raise InputError("invalid-grades", "Input must contain a grades array.", "$.grades")
    grades = [normalize_row(row, index) for index, row in enumerate(rows)]
    seen: set[str] = set()
    for index, item in enumerate(grades):
        if item["id"] in seen:
            raise InputError(
                "duplicate-grade-row",
                "The snapshot contains a duplicate course and section.",
                f"$.grades[{index}]",
            )
        seen.add(item["id"])
    gpa_rows = [item for item in grades if item["included_in_gpa"]]
    gpa_credits = sum(item["credits"] for item in gpa_rows)
    quality_points = sum(
        item["credits"] * item["grade_points"] for item in gpa_rows
    )
    known_final_gpa = round(quality_points / gpa_credits, 3) if gpa_credits else None
    pending = [item["id"] for item in grades if item["pending"]]
    complete = not pending
    calculated_gpa = known_final_gpa if complete else None
    displayed_value = payload.get("displayed_gpa")
    displayed_gpa = (
        finite_number(displayed_value, "$.displayed_gpa")
        if displayed_value not in (None, "")
        else None
    )
    discrepancy = None
    if displayed_gpa is not None and calculated_gpa is not None:
        discrepancy = abs(displayed_gpa - calculated_gpa) > 0.005
    return {
        "schema": OUTPUT_SCHEMA,
        "ok": True,
        "term": term,
        "course_count": len(grades),
        "grades": grades,
        "credits_in_snapshot": round(sum(item["credits"] for item in grades), 3),
        "earned_credits": round(sum(item["earned_credits"] for item in grades), 3),
        "gpa_credits": round(gpa_credits, 3),
        "quality_points": round(quality_points, 3),
        "known_final_gpa": known_final_gpa,
        "calculated_gpa": calculated_gpa,
        "displayed_gpa": displayed_gpa,
        "displayed_gpa_discrepancy": discrepancy,
        "complete": complete,
        "pending_course_ids": pending,
        "calculation_notes": [
            "Letter grades use the packaged Yonsei-style 4.3 scale.",
            "P/NP and S/U affect earned credits but not GPA credits.",
            "W is excluded; I makes the final GPA incomplete.",
            "Repeated-course and program-specific replacement rules are not applied.",
        ],
        "provenance": {
            "mode": "user-supplied-snapshot",
            "captured_at": captured_at,
            "live_system_queried": False,
            "official_transcript_verified": False,
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
