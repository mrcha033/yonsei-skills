#!/usr/bin/env python3
"""Check a normalized Yonsei schedule for deterministic conflicts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DAY_ORDER = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


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


def minutes(value: Any, path: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 1440:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        raise InputError("invalid-clock", "Expected HH:MM clock value.", path)
    hour, minute = (int(part) for part in value.strip().split(":"))
    if hour > 23 or minute > 59:
        raise InputError("invalid-clock", "Clock value is out of range.", path)
    return hour * 60 + minute


def meeting_interval(meeting: Any, path: str) -> dict[str, Any]:
    if not isinstance(meeting, dict):
        raise InputError("invalid-meeting", "Meeting must be an object.", path)
    day = meeting.get("day")
    if day not in DAY_ORDER:
        raise InputError("invalid-weekday", f"Unsupported normalized weekday: {day!r}.", f"{path}.day")
    start = meeting.get("start_minute")
    end = meeting.get("end_minute")
    start_minute = minutes(start if start is not None else meeting.get("start"), f"{path}.start")
    end_minute = minutes(end if end is not None else meeting.get("end"), f"{path}.end")
    if end_minute <= start_minute:
        raise InputError("invalid-meeting-range", "Meeting end must be after start.", path)
    return {
        "day": day,
        "start_minute": start_minute,
        "end_minute": end_minute,
        "campus": meeting.get("campus", "unknown"),
    }


def normalized_courses(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("courses"), list):
        raise InputError("invalid-input", "Input must be an object with a courses array.")
    courses: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(payload["courses"]):
        path = f"$.courses[{index}]"
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise InputError("invalid-course", "Each course needs a string id.", path)
        if raw["id"] in seen_ids:
            raise InputError("duplicate-course-id", f"Duplicate course id: {raw['id']}.", path)
        seen_ids.add(raw["id"])
        meetings = raw.get("meetings", [])
        if not isinstance(meetings, list):
            raise InputError("invalid-meetings", "Course meetings must be an array.", f"{path}.meetings")
        courses.append(
            {
                **raw,
                "meetings": [
                    meeting_interval(item, f"{path}.meetings[{meeting_index}]")
                    for meeting_index, item in enumerate(meetings)
                ],
            }
        )
    return courses


def travel_matrix(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError("invalid-travel-matrix", "travel_minutes must be an object.", "$.travel_minutes")
    result: dict[str, int] = {}
    for route, duration in value.items():
        if not isinstance(route, str) or "->" not in route:
            raise InputError("invalid-travel-route", "Travel keys must look like campus-a->campus-b.")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise InputError("invalid-travel-duration", "Travel durations must be non-negative integers.")
        result[route.lower().replace(" ", "")] = duration
    return result


def conflict_record(
    conflict_type: str,
    course_ids: list[str],
    day: str,
    message: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "type": conflict_type,
        "severity": "error",
        "course_ids": course_ids,
        "day": day,
        "message": message,
        "details": details,
    }


def run(payload: Any) -> dict[str, Any]:
    courses = normalized_courses(payload)
    constraints = payload.get("constraints", {})
    if not isinstance(constraints, dict):
        raise InputError(
            "invalid-constraints",
            "constraints must be an object.",
            "$.constraints",
        )
    travel = travel_matrix(
        payload.get("travel_minutes", constraints.get("travel_minutes"))
    )
    conflicts: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []

    by_code: dict[str, list[str]] = {}
    for course in courses:
        code = course.get("course_code")
        if isinstance(code, str) and code:
            by_code.setdefault(code, []).append(course["id"])
        if not course["meetings"]:
            unknowns.append(
                {
                    "type": "missing-meetings",
                    "course_ids": [course["id"]],
                    "message": "No meeting times supplied.",
                }
            )
    for code, course_ids in sorted(by_code.items()):
        if len(course_ids) > 1:
            conflicts.append(
                conflict_record(
                    "duplicate-course",
                    sorted(course_ids),
                    "",
                    f"Multiple sections of {code} are selected.",
                    course_code=code,
                )
            )

    entries: list[dict[str, Any]] = []
    for course in courses:
        for meeting in course["meetings"]:
            entries.append({"course_id": course["id"], **meeting})
            if meeting["campus"] in {"unknown", "other", ""}:
                unknowns.append(
                    {
                        "type": "unresolved-campus",
                        "course_ids": [course["id"]],
                        "day": meeting["day"],
                        "message": "Meeting campus is unresolved.",
                    }
                )
    entries.sort(
        key=lambda item: (
            DAY_ORDER[item["day"]],
            item["start_minute"],
            item["end_minute"],
            item["course_id"],
        )
    )
    for left_index, left in enumerate(entries):
        for right in entries[left_index + 1 :]:
            if right["day"] != left["day"]:
                if DAY_ORDER[right["day"]] > DAY_ORDER[left["day"]]:
                    break
                continue
            if right["course_id"] == left["course_id"]:
                continue
            if right["start_minute"] < left["end_minute"] and left["start_minute"] < right["end_minute"]:
                conflicts.append(
                    conflict_record(
                        "time-overlap",
                        sorted([left["course_id"], right["course_id"]]),
                        left["day"],
                        "Course meetings overlap.",
                        overlap_start=max(left["start_minute"], right["start_minute"]),
                        overlap_end=min(left["end_minute"], right["end_minute"]),
                    )
                )
                continue
            earlier, later = (
                (left, right)
                if left["end_minute"] <= right["start_minute"]
                else (right, left)
            )
            from_campus = str(earlier.get("campus", "unknown"))
            to_campus = str(later.get("campus", "unknown"))
            if {from_campus, to_campus} & {"unknown", "other", ""}:
                continue
            if from_campus == to_campus or "remote" in {from_campus, to_campus}:
                continue
            route = f"{from_campus}->{to_campus}".lower().replace(" ", "")
            gap = later["start_minute"] - earlier["end_minute"]
            if route not in travel:
                unknowns.append(
                    {
                        "type": "travel-duration-missing",
                        "course_ids": [earlier["course_id"], later["course_id"]],
                        "day": earlier["day"],
                        "route": route,
                        "gap_minutes": gap,
                        "message": "Cross-campus transfer duration was not supplied.",
                    }
                )
            elif gap < travel[route]:
                conflicts.append(
                    conflict_record(
                        "insufficient-travel-time",
                        [earlier["course_id"], later["course_id"]],
                        earlier["day"],
                        "Gap is shorter than the supplied campus-transfer duration.",
                        route=route,
                        gap_minutes=gap,
                        required_minutes=travel[route],
                    )
                )

    blocked = payload.get(
        "blocked_times",
        constraints.get("blocked_times", []),
    )
    if not isinstance(blocked, list):
        raise InputError("invalid-blocked-times", "blocked_times must be an array.", "$.blocked_times")
    for blocked_index, raw_block in enumerate(blocked):
        block = meeting_interval(raw_block, f"$.blocked_times[{blocked_index}]")
        for entry in entries:
            if (
                entry["day"] == block["day"]
                and entry["start_minute"] < block["end_minute"]
                and block["start_minute"] < entry["end_minute"]
            ):
                conflicts.append(
                    conflict_record(
                        "blocked-time-overlap",
                        [entry["course_id"]],
                        entry["day"],
                        "Course overlaps a blocked time.",
                        blocked_index=blocked_index,
                    )
                )

    def stable_key(item: dict[str, Any]) -> str:
        return json.dumps(item, ensure_ascii=False, sort_keys=True)

    conflicts = sorted({stable_key(item): item for item in conflicts}.values(), key=stable_key)
    unknowns = sorted({stable_key(item): item for item in unknowns}.values(), key=stable_key)
    return {
        "schema": "yonsei-schedule-check/v1",
        "ok": True,
        "conflict_free": (
            False
            if conflicts
            else (None if unknowns else True)
        ),
        "no_detected_conflicts": not conflicts,
        "complete": not unknowns,
        "conflicts": conflicts,
        "unknowns": unknowns,
        "course_count": len(courses),
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
