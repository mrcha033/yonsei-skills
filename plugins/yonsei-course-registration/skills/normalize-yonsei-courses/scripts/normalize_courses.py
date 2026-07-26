#!/usr/bin/env python3
"""Normalize supplied Yonsei-style course data without network access."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-normalized-courses/v1"
PLANNING_ENVELOPE_FIELDS = (
    "requirements",
    "fixed_course_ids",
    "constraints",
    "preferences",
    "max_solutions",
    "max_search_states",
    "blocked_times",
    "travel_minutes",
)
DAY_ALIASES = {
    "월": "mon", "월요일": "mon", "mon": "mon", "monday": "mon",
    "화": "tue", "화요일": "tue", "tue": "tue", "tuesday": "tue",
    "수": "wed", "수요일": "wed", "wed": "wed", "wednesday": "wed",
    "목": "thu", "목요일": "thu", "thu": "thu", "thursday": "thu",
    "금": "fri", "금요일": "fri", "fri": "fri", "friday": "fri",
    "토": "sat", "토요일": "sat", "sat": "sat", "saturday": "sat",
    "일": "sun", "일요일": "sun", "sun": "sun", "sunday": "sun",
}
DAY_ORDER = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
CAMPUS_ALIASES = {
    "신촌": "sinchon", "신촌캠퍼스": "sinchon", "sinchon": "sinchon",
    "국제": "international", "국제캠퍼스": "international",
    "송도": "international", "songdo": "international",
    "international": "international",
    "미래": "mirae", "미래캠퍼스": "mirae", "원주": "mirae", "wonju": "mirae",
    "mirae": "mirae",
    "온라인": "remote", "비대면": "remote", "원격": "remote",
    "online": "remote", "remote": "remote",
}
KEYS = {
    "course_code": ("course_code", "courseCode", "code", "학정번호", "교과목번호"),
    "section": ("section", "class_number", "분반"),
    "title": ("title", "course_name", "name", "교과목명", "교과목명(국문)"),
    "instructor": ("instructor", "professor", "담당교수", "교수명"),
    "credits": ("credits", "credit", "학점"),
    "campus": ("campus", "캠퍼스", "개설캠퍼스"),
    "meetings": ("meetings", "meeting_times", "schedule", "강의시간", "수업시간"),
    "source_url": ("source_url", "url", "출처"),
}
MEETING_RE = re.compile(
    r"^(?P<days>[월화수목금토일]+|(?:mon|tue|wed|thu|fri|sat|sun)"
    r"(?:\s*,?\s*(?:mon|tue|wed|thu|fri|sat|sun))*)\s*"
    r"(?P<start>\d{1,2}:\d{2})\s*[-~–]\s*(?P<end>\d{1,2}:\d{2})"
    r"(?:\s*@\s*(?P<campus>.+))?$",
    re.IGNORECASE,
)


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError(
        "invalid-json-number",
        f"Non-finite JSON number is not allowed: {value}.",
    )


def first(row: dict[str, Any], field: str) -> Any:
    for key in KEYS[field]:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def clock_minutes(value: Any, path: str) -> tuple[str, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        raise InputError("invalid-clock", "Expected a clock value such as 09:00.", path)
    hour, minute = (int(part) for part in value.strip().split(":"))
    if hour > 23 or minute > 59:
        raise InputError("invalid-clock", f"Clock value is out of range: {value!r}.", path)
    return f"{hour:02d}:{minute:02d}", hour * 60 + minute


def normalize_day(value: Any, path: str) -> str:
    key = str(value).strip().lower()
    if key not in DAY_ALIASES:
        raise InputError("unknown-weekday", f"Unknown weekday: {value!r}.", path)
    return DAY_ALIASES[key]


def normalize_campus(value: Any) -> tuple[str, str | None]:
    if value in (None, ""):
        return "unknown", None
    raw = str(value).strip()
    return CAMPUS_ALIASES.get(raw.lower(), "other"), raw


def split_days(value: str, path: str) -> list[str]:
    compact = value.strip()
    if re.fullmatch(r"[월화수목금토일]+", compact):
        return [normalize_day(day, path) for day in compact]
    return [
        normalize_day(token, path)
        for token in re.split(r"\s*,\s*|\s+", compact)
        if token
    ]


def structured_meeting(
    item: dict[str, Any], default_campus: Any, path: str
) -> list[dict[str, Any]]:
    days_value = item.get("days", item.get("day"))
    if days_value is None:
        raise InputError("missing-meeting-day", "Meeting day is required.", f"{path}.day")
    raw_days = days_value if isinstance(days_value, list) else [days_value]
    days: list[str] = []
    for index, raw_day in enumerate(raw_days):
        if isinstance(raw_day, str) and re.fullmatch(r"[월화수목금토일]+", raw_day.strip()):
            days.extend(split_days(raw_day, f"{path}.days[{index}]"))
        else:
            days.append(normalize_day(raw_day, f"{path}.days[{index}]"))
    start, start_minute = clock_minutes(item.get("start"), f"{path}.start")
    end, end_minute = clock_minutes(item.get("end"), f"{path}.end")
    if end_minute <= start_minute:
        raise InputError("invalid-meeting-range", "Meeting end must be after start.", path)
    campus, campus_raw = normalize_campus(item.get("campus", default_campus))
    return [
        {
            "day": day,
            "start": start,
            "end": end,
            "start_minute": start_minute,
            "end_minute": end_minute,
            "campus": campus,
            "campus_raw": campus_raw,
            "location": item.get("location"),
        }
        for day in days
    ]


def string_meetings(value: str, default_campus: Any, path: str) -> list[dict[str, Any]]:
    if re.search(r"[월화수목금토일]\s*\d+(?:\s*,\s*\d+)+", value):
        raise InputError(
            "unsupported-period-notation",
            "Period-number notation needs an official period mapping; provide clock ranges.",
            path,
        )
    chunks = [chunk.strip() for chunk in re.split(r"\s*[;/]\s*", value) if chunk.strip()]
    result: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        match = MEETING_RE.fullmatch(chunk)
        if not match:
            raise InputError(
                "invalid-meeting-string",
                f"Could not parse meeting {chunk!r}; use '월수 10:00-11:15'.",
                f"{path}[{index}]",
            )
        result.extend(
            structured_meeting(
                {
                    "days": split_days(match.group("days"), f"{path}[{index}].days"),
                    "start": match.group("start"),
                    "end": match.group("end"),
                    "campus": match.group("campus") or default_campus,
                },
                default_campus,
                f"{path}[{index}]",
            )
        )
    return result


def normalize_meetings(value: Any, campus: Any, path: str) -> list[dict[str, Any]]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        return string_meetings(value, campus, path)
    if not isinstance(value, list):
        raise InputError("invalid-meetings", "Meetings must be a string or array.", path)
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise InputError(
                "invalid-meeting", "Each meeting must be an object.", f"{path}[{index}]"
            )
        result.extend(structured_meeting(item, campus, f"{path}[{index}]"))
    return result


def normalize_course(row: Any, index: int, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    path = f"$.courses[{index}]"
    if not isinstance(row, dict):
        raise InputError("invalid-course", "Each course must be an object.", path)
    code_raw = first(row, "course_code")
    title_raw = first(row, "title")
    if code_raw in (None, ""):
        raise InputError("missing-course-code", "Course code is required.", f"{path}.course_code")
    if title_raw in (None, ""):
        raise InputError("missing-title", "Course title is required.", f"{path}.title")
    course_code = str(code_raw).strip().upper()
    section_value = first(row, "section")
    section = str(section_value).strip() if section_value not in (None, "") else None
    course_id = f"{course_code}-{section}" if section else course_code
    credit_value = first(row, "credits")
    credits: float | None = None
    if credit_value not in (None, ""):
        try:
            credits = float(credit_value)
        except (TypeError, ValueError) as error:
            raise InputError("invalid-credits", "Credits must be numeric.", f"{path}.credits") from error
        if not math.isfinite(credits) or credits < 0:
            raise InputError(
                "invalid-credits",
                "Credits must be a finite non-negative number.",
                f"{path}.credits",
            )
    campus_value = first(row, "campus")
    campus, campus_raw = normalize_campus(campus_value)
    meetings = normalize_meetings(first(row, "meetings"), campus_value, f"{path}.meetings")
    if not meetings:
        warnings.append(
            {
                "code": "missing-meetings",
                "course_id": course_id,
                "message": "No meeting times supplied; downstream conflict checks are incomplete.",
            }
        )
    if campus in {"unknown", "other"} or any(
        meeting["campus"] in {"unknown", "other"} for meeting in meetings
    ):
        warnings.append(
            {
                "code": "unresolved-campus",
                "course_id": course_id,
                "message": "A course or meeting campus is missing or not a recognized Yonsei campus alias.",
            }
        )
    if credits is None:
        warnings.append(
            {
                "code": "missing-credits",
                "course_id": course_id,
                "message": "Credits are missing; total-credit checks are incomplete.",
            }
        )
    return {
        "id": course_id,
        "course_code": course_code,
        "section": section,
        "title": str(title_raw).strip(),
        "instructor": str(first(row, "instructor")).strip()
        if first(row, "instructor") not in (None, "")
        else None,
        "credits": credits,
        "campus": campus,
        "campus_raw": campus_raw,
        "meetings": sorted(
            meetings,
            key=lambda meeting: (
                DAY_ORDER[meeting["day"]],
                meeting["start_minute"],
                meeting["end_minute"],
            ),
        ),
        "source_url": (
            str(first(row, "source_url")).strip()
            if first(row, "source_url") not in (None, "")
            else None
        ),
        "source_index": index,
    }


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("courses"), list):
        raise InputError("invalid-input", "Input must be an object with a courses array.")
    warnings: list[dict[str, Any]] = []
    courses = [
        normalize_course(row, index, warnings)
        for index, row in enumerate(payload["courses"])
    ]
    seen: set[str] = set()
    for index, course in enumerate(courses):
        if course["id"] in seen:
            raise InputError(
                "duplicate-course-id",
                f"Duplicate normalized course ID: {course['id']}.",
                f"$.courses[{index}]",
            )
        seen.add(course["id"])
    result = {
        "schema": OUTPUT_SCHEMA,
        "ok": True,
        "courses": courses,
        "warnings": warnings,
        "provenance": {
            "mode": "user-supplied",
            "official_catalogue_fetched": False,
        },
    }
    for field in PLANNING_ENVELOPE_FIELDS:
        if field in payload:
            result[field] = payload[field]
    return result


def load_input(path: str) -> Any:
    try:
        if path == "-":
            return json.load(sys.stdin, parse_constant=reject_json_constant)
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=reject_json_constant,
        )
    except (OSError, json.JSONDecodeError) as error:
        raise InputError("invalid-json", f"Could not read JSON input: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="JSON file, or - for stdin")
    args = parser.parse_args()
    try:
        output = run(load_input(args.input))
        exit_code = 0
    except InputError as error:
        output = {
            "schema": "yonsei-course-error/v1",
            "ok": False,
            "error": {"code": error.code, "message": str(error), "path": error.path},
        }
        exit_code = 2
    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
