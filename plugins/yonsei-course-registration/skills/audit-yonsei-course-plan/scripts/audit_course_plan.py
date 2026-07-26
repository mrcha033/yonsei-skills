#!/usr/bin/env python3
"""Audit one normalized Yonsei course plan against explicit constraints."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


DAY_ORDER = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


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


def clock_minutes(value: Any, path: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 1440:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        raise InputError("invalid-clock", "Expected HH:MM clock value.", path)
    hour, minute = (int(part) for part in value.strip().split(":"))
    if hour > 23 or minute > 59:
        raise InputError("invalid-clock", "Clock value is out of range.", path)
    return hour * 60 + minute


def numeric_limit(value: Any, path: str) -> float | None:
    if value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise InputError("invalid-limit", "Credit limits must be non-negative numbers.", path)
    return float(value)


def string_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise InputError("invalid-string-list", "Expected an array of strings.", path)
    return [item.strip() for item in value if item.strip()]


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("courses"), list):
        raise InputError("invalid-input", "Input must be an object with a courses array.")
    constraints = payload.get("constraints", {})
    if not isinstance(constraints, dict):
        raise InputError("invalid-constraints", "constraints must be an object.", "$.constraints")
    min_credits = numeric_limit(constraints.get("min_credits"), "$.constraints.min_credits")
    max_credits = numeric_limit(constraints.get("max_credits"), "$.constraints.max_credits")
    if min_credits is not None and max_credits is not None and min_credits > max_credits:
        raise InputError("invalid-credit-range", "min_credits cannot exceed max_credits.")
    required_codes = {
        item.upper()
        for item in string_list(
            constraints.get("required_course_codes"), "$.constraints.required_course_codes"
        )
    }
    allowed_campuses = set(
        string_list(constraints.get("allowed_campuses"), "$.constraints.allowed_campuses")
    )
    days_off = set(string_list(constraints.get("days_off"), "$.constraints.days_off"))
    if not days_off.issubset(DAY_ORDER):
        raise InputError("invalid-days-off", "days_off must use mon through sun.", "$.constraints.days_off")
    earliest = (
        clock_minutes(constraints["earliest_start"], "$.constraints.earliest_start")
        if constraints.get("earliest_start") is not None
        else None
    )
    latest = (
        clock_minutes(constraints["latest_end"], "$.constraints.latest_end")
        if constraints.get("latest_end") is not None
        else None
    )
    max_daily = constraints.get("max_daily_minutes")
    if max_daily is not None and (
        not isinstance(max_daily, int) or isinstance(max_daily, bool) or max_daily < 0
    ):
        raise InputError(
            "invalid-daily-limit",
            "max_daily_minutes must be a non-negative integer.",
            "$.constraints.max_daily_minutes",
        )

    total_credits = 0.0
    by_campus: dict[str, float] = {}
    daily_minutes = {day: 0 for day in DAY_ORDER}
    selected_codes: set[str] = set()
    violations: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []

    for index, course in enumerate(payload["courses"]):
        path = f"$.courses[{index}]"
        if not isinstance(course, dict) or not isinstance(course.get("id"), str):
            raise InputError("invalid-course", "Each course needs a string id.", path)
        course_id = course["id"]
        code = course.get("course_code")
        if isinstance(code, str) and code:
            selected_codes.add(code.upper())
        else:
            unknowns.append(
                {"type": "missing-course-code", "course_id": course_id}
            )
        credits = course.get("credits")
        if credits is None:
            unknowns.append({"type": "missing-credits", "course_id": course_id})
        elif (
            not isinstance(credits, (int, float))
            or isinstance(credits, bool)
            or not math.isfinite(float(credits))
            or credits < 0
        ):
            raise InputError("invalid-credits", "Course credits must be non-negative numeric values.", f"{path}.credits")
        else:
            credit_number = float(credits)
            total_credits += credit_number
            campus = str(course.get("campus", "unknown"))
            by_campus[campus] = by_campus.get(campus, 0.0) + credit_number
        campus = str(course.get("campus", "unknown"))
        if campus in {"unknown", "other", ""}:
            unknowns.append({"type": "unresolved-campus", "course_id": course_id})
        meetings = course.get("meetings", [])
        if not isinstance(meetings, list):
            raise InputError("invalid-meetings", "Course meetings must be an array.", f"{path}.meetings")
        if not meetings:
            unknowns.append({"type": "missing-meetings", "course_id": course_id})
            if allowed_campuses and campus not in allowed_campuses:
                violations.append(
                    {
                        "type": "campus-not-allowed",
                        "course_id": course_id,
                        "campus": campus,
                    }
                )
        for meeting_index, meeting in enumerate(meetings):
            meeting_path = f"{path}.meetings[{meeting_index}]"
            if not isinstance(meeting, dict) or meeting.get("day") not in DAY_ORDER:
                raise InputError("invalid-meeting", "Meeting needs a normalized day.", meeting_path)
            day = meeting["day"]
            meeting_campus = str(meeting.get("campus", campus))
            if meeting_campus in {"unknown", "other", ""}:
                unknowns.append(
                    {
                        "type": "unresolved-meeting-campus",
                        "course_id": course_id,
                        "meeting_index": meeting_index,
                    }
                )
            if allowed_campuses and meeting_campus not in allowed_campuses:
                violations.append(
                    {
                        "type": "campus-not-allowed",
                        "course_id": course_id,
                        "meeting_index": meeting_index,
                        "day": day,
                        "campus": meeting_campus,
                    }
                )
            start = clock_minutes(
                meeting.get("start_minute", meeting.get("start")), f"{meeting_path}.start"
            )
            end = clock_minutes(
                meeting.get("end_minute", meeting.get("end")), f"{meeting_path}.end"
            )
            if end <= start:
                raise InputError("invalid-meeting-range", "Meeting end must be after start.", meeting_path)
            daily_minutes[day] += end - start
            if day in days_off:
                violations.append(
                    {"type": "day-off-violation", "course_id": course_id, "day": day}
                )
            if earliest is not None and start < earliest:
                violations.append(
                    {
                        "type": "starts-too-early",
                        "course_id": course_id,
                        "day": day,
                        "start_minute": start,
                        "earliest_start": earliest,
                    }
                )
            if latest is not None and end > latest:
                violations.append(
                    {
                        "type": "ends-too-late",
                        "course_id": course_id,
                        "day": day,
                        "end_minute": end,
                        "latest_end": latest,
                    }
                )

    total_credits = round(total_credits, 4)
    if min_credits is not None and total_credits < min_credits:
        violations.append(
            {"type": "below-min-credits", "actual": total_credits, "required": min_credits}
        )
    if max_credits is not None and total_credits > max_credits:
        violations.append(
            {"type": "above-max-credits", "actual": total_credits, "allowed": max_credits}
        )
    for code in sorted(required_codes - selected_codes):
        violations.append({"type": "required-course-missing", "course_code": code})
    if max_daily is not None:
        for day in DAY_ORDER:
            if daily_minutes[day] > max_daily:
                violations.append(
                    {
                        "type": "daily-load-exceeded",
                        "day": day,
                        "actual_minutes": daily_minutes[day],
                        "allowed_minutes": max_daily,
                    }
                )

    sort_key = lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True)
    return {
        "schema": "yonsei-course-plan-audit/v1",
        "ok": True,
        "total_credits": total_credits,
        "credits_by_campus": {
            key: round(value, 4) for key, value in sorted(by_campus.items())
        },
        "daily_class_minutes": daily_minutes,
        "selected_course_codes": sorted(selected_codes),
        "constraints_met": not violations and not unknowns,
        "complete": not unknowns,
        "violations": sorted(violations, key=sort_key),
        "unknowns": sorted(unknowns, key=sort_key),
    }


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
