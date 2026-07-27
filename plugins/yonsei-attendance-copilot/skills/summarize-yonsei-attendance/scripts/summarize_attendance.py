#!/usr/bin/env python3
"""Summarize a user-supplied Yonsei electronic-attendance snapshot."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-attendance-summary/v1"
ERROR_SCHEMA = "yonsei-attendance-snapshot-error/v1"
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
    "attendance_code",
    "beacon",
    "location_token",
}
STATUS_ALIASES = {
    "출석": "present",
    "present": "present",
    "o": "present",
    "○": "present",
    "지각": "late",
    "late": "late",
    "결석": "absent",
    "absent": "absent",
    "x": "absent",
    "×": "absent",
    "조퇴": "early-leave",
    "early-leave": "early-leave",
    "early_leave": "early-leave",
    "공결": "excused",
    "유고결석": "excused",
    "인정": "excused",
    "excused": "excused",
    "미처리": "pending",
    "미확정": "pending",
    "pending": "pending",
}
STATUSES = ("present", "late", "absent", "early-leave", "excused", "pending")
KEYS = {
    "course_code": ("course_code", "courseCode", "code", "학정번호", "교과목번호"),
    "course_title": ("course_title", "title", "course_name", "교과목명"),
    "class_date": ("class_date", "date", "수업일", "수업일자"),
    "status": ("status", "attendance_status", "출결상태", "출결"),
    "session_id": ("session_id", "period", "차시", "교시"),
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
                    "credential-or-checkin-field-not-allowed",
                    "Credential, session, location, beacon, and check-in fields are not accepted.",
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


def normalize_date(value: Any, path: str) -> str:
    text = required_text(value, path)
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise InputError("invalid-date", "Use an ISO date such as 2026-03-05.", path) from error


def normalize_status(value: Any, path: str) -> tuple[str, str]:
    displayed = required_text(value, path)
    key = displayed.lower().replace("_", "-")
    if key not in STATUS_ALIASES:
        raise InputError(
            "unknown-attendance-status",
            "Attendance status is not recognized.",
            path,
        )
    return STATUS_ALIASES[key], displayed


def normalize_record(row: Any, index: int) -> dict[str, Any]:
    path = f"$.records[{index}]"
    if not isinstance(row, dict):
        raise InputError("invalid-record", "Each attendance record must be an object.", path)
    code = required_text(first(row, "course_code"), f"{path}.course_code").upper()
    title = required_text(first(row, "course_title"), f"{path}.course_title")
    class_date = normalize_date(first(row, "class_date"), f"{path}.class_date")
    status, displayed = normalize_status(first(row, "status"), f"{path}.status")
    session_value = first(row, "session_id")
    session_id = str(session_value).strip() if session_value not in (None, "") else None
    return {
        "id": "|".join((code, class_date, session_id or "unspecified")),
        "course_code": code,
        "course_title": title,
        "class_date": class_date,
        "session_id": session_id,
        "status": status,
        "status_displayed": displayed,
        "source_index": index,
    }


def empty_totals() -> dict[str, int]:
    return {status: 0 for status in STATUSES}


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be a JSON object.")
    scan_credentials(payload)
    captured_at = required_text(payload.get("captured_at"), "$.captured_at")
    rows = payload.get("records")
    if not isinstance(rows, list):
        raise InputError("invalid-records", "Input must contain a records array.", "$.records")
    records = [normalize_record(row, index) for index, row in enumerate(rows)]
    seen: set[str] = set()
    for index, record in enumerate(records):
        if record["id"] in seen:
            raise InputError(
                "duplicate-attendance-record",
                "Duplicate course/date/session attendance record.",
                f"$.records[{index}]",
            )
        seen.add(record["id"])
    records.sort(key=lambda item: (item["class_date"], item["course_code"], item["id"]))
    totals = empty_totals()
    course_map: dict[str, dict[str, Any]] = {}
    for record in records:
        totals[record["status"]] += 1
        course = course_map.setdefault(
            record["course_code"],
            {
                "course_code": record["course_code"],
                "course_title": record["course_title"],
                "record_count": 0,
                "totals": empty_totals(),
            },
        )
        if course["course_title"] != record["course_title"]:
            raise InputError(
                "course-title-conflict",
                "One course code has conflicting titles in the snapshot.",
                f"$.records[{record['source_index']}].course_title",
            )
        course["record_count"] += 1
        course["totals"][record["status"]] += 1
    dates = [record["class_date"] for record in records]
    return {
        "schema": OUTPUT_SCHEMA,
        "ok": True,
        "record_count": len(records),
        "date_range": {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
        },
        "totals": totals,
        "attention_count": totals["late"] + totals["absent"] + totals["early-leave"],
        "by_course": [course_map[key] for key in sorted(course_map)],
        "records": records,
        "complete": True,
        "actions": {
            "checkin_performed": False,
            "correction_submitted": False,
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
