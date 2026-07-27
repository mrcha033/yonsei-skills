#!/usr/bin/env python3
"""Find explicit discrepancies in a user-supplied attendance snapshot."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-attendance-discrepancy-report/v1"
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
    "location",
    "latitude",
    "longitude",
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
KEYS = {
    "course_code": ("course_code", "courseCode", "code", "학정번호", "교과목번호"),
    "course_title": ("course_title", "title", "course_name", "교과목명"),
    "class_date": ("class_date", "date", "수업일", "수업일자"),
    "recorded_status": ("recorded_status", "status", "출결상태", "기록상태"),
    "expected_status": ("expected_status", "requested_status", "기대상태", "요청상태"),
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "credential-or-presence-field-not-allowed",
                    "Credential, session, location, beacon, and check-in fields are not accepted.",
                    f"{path}.{key}",
                )
            scan_forbidden(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_forbidden(item, f"{path}[{index}]")


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "A non-empty text value is required.", path)
    return value.strip()


def optional_text(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise InputError("invalid-text", "Expected text.", path)
    return value.strip() or None


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


def normalize_status(value: Any, path: str, *, optional: bool = False) -> str | None:
    if optional and value in (None, ""):
        return None
    displayed = required_text(value, path)
    key = displayed.lower().replace("_", "-")
    if key not in STATUS_ALIASES:
        raise InputError(
            "unknown-attendance-status",
            "Attendance status is not recognized.",
            path,
        )
    return STATUS_ALIASES[key]


def boolean(value: Any, path: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise InputError("invalid-boolean", "Expected true or false.", path)
    return value


def evidence_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InputError("invalid-evidence", "Evidence must be an array of descriptions.", path)
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(required_text(item, f"{path}[{index}]"))
    return result


def normalize_record(row: Any, index: int) -> dict[str, Any]:
    path = f"$.records[{index}]"
    if not isinstance(row, dict):
        raise InputError("invalid-record", "Each review record must be an object.", path)
    code = required_text(first(row, "course_code"), f"{path}.course_code").upper()
    title = required_text(first(row, "course_title"), f"{path}.course_title")
    class_date = normalize_date(first(row, "class_date"), f"{path}.class_date")
    recorded = normalize_status(
        first(row, "recorded_status"), f"{path}.recorded_status"
    )
    expected = normalize_status(
        first(row, "expected_status"),
        f"{path}.expected_status",
        optional=True,
    )
    disputed = boolean(row.get("user_disputed"), f"{path}.user_disputed")
    reviewed = boolean(row.get("reviewed"), f"{path}.reviewed")
    reason = optional_text(row.get("reason"), f"{path}.reason")
    evidence = evidence_list(row.get("evidence"), f"{path}.evidence")
    reviewed = reviewed or disputed or expected is not None
    is_discrepancy = disputed or (expected is not None and expected != recorded)
    return {
        "id": "|".join((code, class_date)),
        "course_code": code,
        "course_title": title,
        "class_date": class_date,
        "recorded_status": recorded,
        "expected_status": expected,
        "user_disputed": disputed,
        "reviewed": reviewed,
        "reason": reason,
        "evidence": evidence,
        "is_discrepancy": is_discrepancy,
        "ready_for_draft": bool(
            is_discrepancy
            and expected is not None
            and expected != recorded
            and reason
            and evidence
        ),
        "source_index": index,
    }


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be a JSON object.")
    scan_forbidden(payload)
    captured_at = required_text(payload.get("captured_at"), "$.captured_at")
    rows = payload.get("records")
    if not isinstance(rows, list):
        raise InputError("invalid-records", "Input must contain a records array.", "$.records")
    normalized = [normalize_record(row, index) for index, row in enumerate(rows)]
    seen: set[str] = set()
    for index, record in enumerate(normalized):
        if record["id"] in seen:
            raise InputError(
                "duplicate-review-record",
                "Duplicate course/date review record.",
                f"$.records[{index}]",
            )
        seen.add(record["id"])
    discrepancies = [
        {key: value for key, value in record.items() if key != "is_discrepancy"}
        for record in normalized
        if record["is_discrepancy"]
    ]
    unknowns = [
        {
            "course_code": record["course_code"],
            "course_title": record["course_title"],
            "class_date": record["class_date"],
            "reason": "This row has no expected status and was not marked reviewed.",
        }
        for record in normalized
        if not record["reviewed"]
    ]
    review_complete = not unknowns
    return {
        "schema": OUTPUT_SCHEMA,
        "ok": True,
        "reviewed_record_count": sum(record["reviewed"] for record in normalized),
        "discrepancy_count": len(discrepancies),
        "ready_for_draft_count": sum(item["ready_for_draft"] for item in discrepancies),
        "discrepancies": discrepancies,
        "unknowns": unknowns,
        "review_complete": review_complete,
        "no_discrepancies_found": review_complete and not discrepancies,
        "actions": {
            "presence_inferred": False,
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
