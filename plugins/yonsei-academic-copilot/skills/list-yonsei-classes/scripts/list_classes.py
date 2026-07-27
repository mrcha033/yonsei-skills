#!/usr/bin/env python3
"""Normalize a user-supplied Yonsei academic class snapshot."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-academic-class-list/v1"
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
DAY_ALIASES = {
    "월": "mon",
    "월요일": "mon",
    "mon": "mon",
    "monday": "mon",
    "화": "tue",
    "화요일": "tue",
    "tue": "tue",
    "tuesday": "tue",
    "수": "wed",
    "수요일": "wed",
    "wed": "wed",
    "wednesday": "wed",
    "목": "thu",
    "목요일": "thu",
    "thu": "thu",
    "thursday": "thu",
    "금": "fri",
    "금요일": "fri",
    "fri": "fri",
    "friday": "fri",
    "토": "sat",
    "토요일": "sat",
    "sat": "sat",
    "saturday": "sat",
    "일": "sun",
    "일요일": "sun",
    "sun": "sun",
    "sunday": "sun",
}
DAY_ORDER = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
KEYS = {
    "course_code": ("course_code", "courseCode", "code", "학정번호", "교과목번호"),
    "section": ("section", "class_number", "분반"),
    "title": ("title", "course_name", "name", "교과목명", "교과목명(국문)"),
    "instructor": ("instructor", "professor", "담당교수", "교수명"),
    "credits": ("credits", "credit", "학점"),
    "meetings": ("meetings", "meeting_times", "강의시간"),
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


def clock(value: Any, path: str) -> tuple[str, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        raise InputError("invalid-clock", "Use a clock value such as 09:00.", path)
    hour, minute = (int(part) for part in value.strip().split(":"))
    if hour > 23 or minute > 59:
        raise InputError("invalid-clock", "Clock value is out of range.", path)
    return f"{hour:02d}:{minute:02d}", hour * 60 + minute


def normalize_day(value: Any, path: str) -> str:
    key = str(value).strip().lower()
    if key not in DAY_ALIASES:
        raise InputError("unknown-weekday", "Meeting weekday is not recognized.", path)
    return DAY_ALIASES[key]


def normalize_meetings(value: Any, path: str) -> tuple[list[dict[str, Any]], str | None]:
    if value in (None, "", []):
        return [], None
    if isinstance(value, str):
        return [], value.strip()
    if not isinstance(value, list):
        raise InputError(
            "invalid-meetings",
            "Meetings must be an array of day/start/end objects.",
            path,
        )
    meetings: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            raise InputError("invalid-meeting", "Each meeting must be an object.", item_path)
        day = normalize_day(item.get("day"), f"{item_path}.day")
        start, start_minute = clock(item.get("start"), f"{item_path}.start")
        end, end_minute = clock(item.get("end"), f"{item_path}.end")
        if end_minute <= start_minute:
            raise InputError(
                "invalid-meeting-range",
                "Meeting end must be after meeting start.",
                item_path,
            )
        location = item.get("location")
        if location is not None and not isinstance(location, str):
            raise InputError("invalid-location", "Location must be text.", f"{item_path}.location")
        meetings.append(
            {
                "day": day,
                "start": start,
                "end": end,
                "start_minute": start_minute,
                "end_minute": end_minute,
                "location": location.strip() if isinstance(location, str) else None,
            }
        )
    return (
        sorted(
            meetings,
            key=lambda item: (
                DAY_ORDER[item["day"]],
                item["start_minute"],
                item["end_minute"],
            ),
        ),
        None,
    )


def normalize_class(
    row: Any, index: int, warnings: list[dict[str, Any]]
) -> dict[str, Any]:
    path = f"$.classes[{index}]"
    if not isinstance(row, dict):
        raise InputError("invalid-class", "Each class must be an object.", path)
    course_code = required_text(first(row, "course_code"), f"{path}.course_code").upper()
    title = required_text(first(row, "title"), f"{path}.title")
    section_value = first(row, "section")
    section = str(section_value).strip() if section_value not in (None, "") else None
    class_id = f"{course_code}-{section}" if section else course_code
    instructor_value = first(row, "instructor")
    instructor = (
        str(instructor_value).strip()
        if instructor_value not in (None, "")
        else None
    )
    credits_value = first(row, "credits")
    credits: float | None = None
    if credits_value not in (None, ""):
        if isinstance(credits_value, bool):
            raise InputError("invalid-credits", "Credits must be numeric.", f"{path}.credits")
        try:
            credits = float(credits_value)
        except (TypeError, ValueError) as error:
            raise InputError(
                "invalid-credits", "Credits must be numeric.", f"{path}.credits"
            ) from error
        if not math.isfinite(credits) or credits < 0:
            raise InputError(
                "invalid-credits",
                "Credits must be finite and non-negative.",
                f"{path}.credits",
            )
    meetings, schedule_text = normalize_meetings(
        first(row, "meetings"), f"{path}.meetings"
    )
    if not meetings:
        warnings.append(
            {
                "code": "structured-meetings-missing",
                "class_id": class_id,
                "message": (
                    "No structured meeting objects were supplied."
                    if schedule_text is None
                    else "Schedule text was preserved but not interpreted."
                ),
            }
        )
    return {
        "id": class_id,
        "course_code": course_code,
        "section": section,
        "title": title,
        "instructor": instructor,
        "credits": credits,
        "meetings": meetings,
        "schedule_text": schedule_text,
        "source_index": index,
    }


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be a JSON object.")
    scan_credentials(payload)
    captured_at = required_text(payload.get("captured_at"), "$.captured_at")
    term = required_text(payload.get("term"), "$.term")
    rows = payload.get("classes")
    if not isinstance(rows, list):
        raise InputError("invalid-classes", "Input must contain a classes array.", "$.classes")
    warnings: list[dict[str, Any]] = []
    classes = [normalize_class(row, index, warnings) for index, row in enumerate(rows)]
    seen: set[str] = set()
    for index, item in enumerate(classes):
        if item["id"] in seen:
            raise InputError(
                "duplicate-class-id",
                "The snapshot contains a duplicate course and section.",
                f"$.classes[{index}]",
            )
        seen.add(item["id"])
    classes.sort(
        key=lambda item: (
            DAY_ORDER[item["meetings"][0]["day"]]
            if item["meetings"]
            else 99,
            item["meetings"][0]["start_minute"] if item["meetings"] else 99_999,
            item["id"],
        )
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "ok": True,
        "term": term,
        "class_count": len(classes),
        "classes": classes,
        "complete": not warnings,
        "warnings": warnings,
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
