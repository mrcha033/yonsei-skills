#!/usr/bin/env python3
"""Build conflict-free timetables from normalized Yonsei course choices."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


DAY_ORDER = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DEFAULT_MAX_STATES = 100_000


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


class SearchLimitError(RuntimeError):
    pass


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


def string_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise InputError("invalid-string-list", "Expected an array of strings.", path)
    result = [item.strip() for item in value if item.strip()]
    if len(result) != len(set(result)):
        raise InputError("duplicate-list-value", "Array values must be unique.", path)
    return result


def numeric_limit(value: Any, path: str) -> float | None:
    if value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise InputError("invalid-credit-limit", "Credit limits must be non-negative numbers.", path)
    return float(value)


def parse_meeting(
    raw: Any, path: str, *, require_campus: bool = True
) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("day") not in DAY_ORDER:
        raise InputError("invalid-meeting", "Meeting needs a normalized day.", path)
    start = clock_minutes(raw.get("start_minute", raw.get("start")), f"{path}.start")
    end = clock_minutes(raw.get("end_minute", raw.get("end")), f"{path}.end")
    if end <= start:
        raise InputError("invalid-meeting-range", "Meeting end must be after start.", path)
    campus = str(raw.get("campus", "unknown"))
    if require_campus and campus in {"unknown", "other", ""}:
        raise InputError("unresolved-campus", "Timetable construction requires a resolved campus.", f"{path}.campus")
    return {"day": raw["day"], "start": start, "end": end, "campus": campus}


def parse_courses(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_courses = payload.get("courses")
    if not isinstance(raw_courses, list):
        raise InputError("invalid-input", "Input must contain a courses array.")
    courses: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_courses):
        path = f"$.courses[{index}]"
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            raise InputError("invalid-course", "Each course needs a non-empty string id.", path)
        course_id = raw["id"]
        if course_id in courses:
            raise InputError("duplicate-course-id", f"Duplicate course id: {course_id}.", path)
        credits = raw.get("credits")
        if (
            not isinstance(credits, (int, float))
            or isinstance(credits, bool)
            or not math.isfinite(float(credits))
            or credits < 0
        ):
            raise InputError(
                "missing-or-invalid-credits",
                "Every timetable candidate needs non-negative numeric credits.",
                f"{path}.credits",
            )
        raw_meetings = raw.get("meetings")
        if not isinstance(raw_meetings, list) or not raw_meetings:
            raise InputError(
                "missing-meetings",
                "Every timetable candidate needs at least one meeting.",
                f"{path}.meetings",
            )
        meetings = [
            parse_meeting(item, f"{path}.meetings[{meeting_index}]")
            for meeting_index, item in enumerate(raw_meetings)
        ]
        for left_index, left in enumerate(meetings):
            for right in meetings[left_index + 1 :]:
                if (
                    left["day"] == right["day"]
                    and left["start"] < right["end"]
                    and right["start"] < left["end"]
                ):
                    raise InputError(
                        "self-overlapping-course",
                        f"Course {course_id} has overlapping meetings.",
                        f"{path}.meetings",
                    )
        code = raw.get("course_code")
        courses[course_id] = {
            "id": course_id,
            "course_code": str(code).upper() if isinstance(code, str) and code else course_id,
            "title": raw.get("title"),
            "credits": float(credits),
            "meetings": meetings,
        }
    return courses


def parse_travel(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError("invalid-travel-matrix", "travel_minutes must be an object.")
    result: dict[str, int] = {}
    for route, duration in value.items():
        if not isinstance(route, str) or "->" not in route:
            raise InputError("invalid-travel-route", "Travel keys must look like campus-a->campus-b.")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
            raise InputError("invalid-travel-duration", "Travel durations must be non-negative integers.")
        result[route.lower().replace(" ", "")] = duration
    return result


def pair_compatible(
    left: dict[str, Any], right: dict[str, Any], travel: dict[str, int]
) -> tuple[bool, str | None]:
    if left["course_code"] == right["course_code"]:
        return False, "duplicate-course"
    for left_meeting in left["meetings"]:
        for right_meeting in right["meetings"]:
            if left_meeting["day"] != right_meeting["day"]:
                continue
            if (
                left_meeting["start"] < right_meeting["end"]
                and right_meeting["start"] < left_meeting["end"]
            ):
                return False, "time-overlap"
            earlier, later = (
                (left_meeting, right_meeting)
                if left_meeting["end"] <= right_meeting["start"]
                else (right_meeting, left_meeting)
            )
            if earlier["campus"] == later["campus"] or "remote" in {
                earlier["campus"],
                later["campus"],
            }:
                continue
            route = f"{earlier['campus']}->{later['campus']}".lower().replace(" ", "")
            if route not in travel:
                return False, f"missing-travel:{route}"
            if later["start"] - earlier["end"] < travel[route]:
                return False, "insufficient-travel"
    return True, None


def hard_course_reason(
    course: dict[str, Any],
    constraints: dict[str, Any],
    blocked: list[dict[str, Any]],
) -> str | None:
    allowed_campuses = constraints["allowed_campuses"]
    for meeting in course["meetings"]:
        if meeting["day"] in constraints["days_off"]:
            return "day-off"
        if constraints["earliest_start"] is not None and meeting["start"] < constraints["earliest_start"]:
            return "starts-too-early"
        if constraints["latest_end"] is not None and meeting["end"] > constraints["latest_end"]:
            return "ends-too-late"
        if allowed_campuses and meeting["campus"] not in allowed_campuses:
            return "campus-not-allowed"
        for window in blocked:
            if (
                meeting["day"] == window["day"]
                and meeting["start"] < window["end"]
                and window["start"] < meeting["end"]
            ):
                return "blocked-time"
    return None


def solution_score(
    selected: list[dict[str, Any]], weights: dict[str, float]
) -> tuple[Any, ...]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for course in selected:
        for meeting in course["meetings"]:
            by_day.setdefault(meeting["day"], []).append(meeting)
    gap_minutes = 0
    campus_changes = 0
    for meetings in by_day.values():
        ordered = sorted(meetings, key=lambda item: (item["start"], item["end"], item["campus"]))
        for left, right in zip(ordered, ordered[1:]):
            gap_minutes += max(0, right["start"] - left["end"])
            if left["campus"] != right["campus"] and "remote" not in {
                left["campus"],
                right["campus"],
            }:
                campus_changes += 1
    preference_weight = sum(weights.get(course["id"], 0.0) for course in selected)
    credits = sum(course["credits"] for course in selected)
    ids = tuple(sorted(course["id"] for course in selected))
    return (campus_changes, len(by_day), gap_minutes, -preference_weight, -credits, ids)


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be a JSON object.")
    courses = parse_courses(payload)
    raw_requirements = payload.get("requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise InputError("missing-requirements", "At least one requirement group is required.", "$.requirements")
    requirements: list[dict[str, Any]] = []
    option_owners: dict[str, str] = {}
    seen_requirement_ids: set[str] = set()
    for index, raw in enumerate(raw_requirements):
        path = f"$.requirements[{index}]"
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            raise InputError("invalid-requirement", "Requirement needs a non-empty string id.", path)
        requirement_id = raw["id"]
        if requirement_id in seen_requirement_ids:
            raise InputError("duplicate-requirement-id", f"Duplicate requirement id: {requirement_id}.", path)
        seen_requirement_ids.add(requirement_id)
        options = string_list(raw.get("course_ids"), f"{path}.course_ids")
        if not options:
            raise InputError("empty-requirement", "Requirement needs at least one course option.", path)
        for option in options:
            if option not in courses:
                raise InputError("unknown-course-id", f"Unknown course id: {option}.", f"{path}.course_ids")
            if option in option_owners:
                raise InputError(
                    "course-in-multiple-requirements",
                    f"Course {option} appears in both {option_owners[option]} and {requirement_id}.",
                    f"{path}.course_ids",
                )
            option_owners[option] = requirement_id
        requirements.append(
            {"id": requirement_id, "course_ids": sorted(options), "required": raw.get("required", True) is not False}
        )

    fixed_ids = string_list(payload.get("fixed_course_ids"), "$.fixed_course_ids")
    for course_id in fixed_ids:
        if course_id not in courses:
            raise InputError("unknown-fixed-course", f"Unknown fixed course id: {course_id}.")
        if course_id in option_owners:
            raise InputError(
                "fixed-course-in-requirement",
                f"Fixed course {course_id} also appears in a requirement.",
            )
    constraints_raw = payload.get("constraints", {})
    if not isinstance(constraints_raw, dict):
        raise InputError("invalid-constraints", "constraints must be an object.")
    min_credits = numeric_limit(constraints_raw.get("min_credits"), "$.constraints.min_credits")
    max_credits = numeric_limit(constraints_raw.get("max_credits"), "$.constraints.max_credits")
    if min_credits is not None and max_credits is not None and min_credits > max_credits:
        raise InputError("invalid-credit-range", "min_credits cannot exceed max_credits.")
    days_off = set(string_list(constraints_raw.get("days_off"), "$.constraints.days_off"))
    if not days_off.issubset(DAY_ORDER):
        raise InputError("invalid-days-off", "days_off must use mon through sun.")
    allowed_campuses = set(
        string_list(constraints_raw.get("allowed_campuses"), "$.constraints.allowed_campuses")
    )
    earliest = (
        clock_minutes(constraints_raw["earliest_start"], "$.constraints.earliest_start")
        if constraints_raw.get("earliest_start") is not None
        else None
    )
    latest = (
        clock_minutes(constraints_raw["latest_end"], "$.constraints.latest_end")
        if constraints_raw.get("latest_end") is not None
        else None
    )
    travel = parse_travel(constraints_raw.get("travel_minutes"))
    raw_blocked = constraints_raw.get("blocked_times", [])
    if not isinstance(raw_blocked, list):
        raise InputError("invalid-blocked-times", "blocked_times must be an array.")
    blocked = [
        parse_meeting(
            item,
            f"$.constraints.blocked_times[{index}]",
            require_campus=False,
        )
        for index, item in enumerate(raw_blocked)
    ]
    constraints = {
        "min_credits": min_credits,
        "max_credits": max_credits,
        "days_off": days_off,
        "allowed_campuses": allowed_campuses,
        "earliest_start": earliest,
        "latest_end": latest,
    }
    preferences = payload.get("preferences", {})
    if not isinstance(preferences, dict):
        raise InputError("invalid-preferences", "preferences must be an object.")
    raw_weights = preferences.get("course_weights", {})
    if not isinstance(raw_weights, dict):
        raise InputError("invalid-course-weights", "course_weights must be an object.")
    weights: dict[str, float] = {}
    for course_id, weight in raw_weights.items():
        if (
            course_id not in courses
            or not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or not math.isfinite(float(weight))
        ):
            raise InputError("invalid-course-weight", "Each course weight needs a known course id and numeric value.")
        weights[course_id] = float(weight)
    max_solutions = payload.get("max_solutions", 10)
    if not isinstance(max_solutions, int) or isinstance(max_solutions, bool) or not 1 <= max_solutions <= 50:
        raise InputError("invalid-max-solutions", "max_solutions must be between 1 and 50.")
    max_states = payload.get("max_search_states", DEFAULT_MAX_STATES)
    if not isinstance(max_states, int) or isinstance(max_states, bool) or not 1 <= max_states <= 1_000_000:
        raise InputError("invalid-max-search-states", "max_search_states must be between 1 and 1000000.")

    rejection_counts: Counter[str] = Counter()
    selected_fixed = [courses[course_id] for course_id in sorted(fixed_ids)]
    for course in selected_fixed:
        reason = hard_course_reason(course, constraints, blocked)
        if reason:
            return {
                "schema": "yonsei-timetable-build/v1",
                "ok": True,
                "feasible": False,
                "solutions": [],
                "searched_states": 0,
                "rejection_counts": {f"fixed:{reason}": 1},
            }
    for left_index, left in enumerate(selected_fixed):
        for right in selected_fixed[left_index + 1 :]:
            compatible, reason = pair_compatible(left, right, travel)
            if not compatible:
                return {
                    "schema": "yonsei-timetable-build/v1",
                    "ok": True,
                    "feasible": False,
                    "solutions": [],
                    "searched_states": 0,
                    "rejection_counts": {f"fixed:{reason}": 1},
                }

    solutions: list[list[dict[str, Any]]] = []
    states = 0

    def search(requirement_index: int, selected: list[dict[str, Any]], credits: float) -> None:
        nonlocal states
        states += 1
        if states > max_states:
            raise SearchLimitError
        if max_credits is not None and credits > max_credits:
            rejection_counts["above-max-credits"] += 1
            return
        if requirement_index == len(requirements):
            if min_credits is not None and credits < min_credits:
                rejection_counts["below-min-credits"] += 1
                return
            solutions.append(list(selected))
            return
        requirement = requirements[requirement_index]
        options: list[str | None] = list(requirement["course_ids"])
        if not requirement["required"]:
            options.append(None)
        for option in options:
            if option is None:
                search(requirement_index + 1, selected, credits)
                continue
            course = courses[option]
            reason = hard_course_reason(course, constraints, blocked)
            if reason:
                rejection_counts[reason] += 1
                continue
            incompatible_reason: str | None = None
            for existing in selected:
                compatible, pair_reason = pair_compatible(existing, course, travel)
                if not compatible:
                    incompatible_reason = pair_reason
                    break
            if incompatible_reason:
                rejection_counts[incompatible_reason] += 1
                continue
            selected.append(course)
            search(requirement_index + 1, selected, credits + course["credits"])
            selected.pop()

    try:
        search(
            0,
            list(selected_fixed),
            sum(course["credits"] for course in selected_fixed),
        )
    except SearchLimitError as error:
        raise InputError(
            "search-space-too-large",
            f"Search exceeded {max_states} states; narrow requirement options or raise max_search_states.",
        ) from error

    ranked = sorted(solutions, key=lambda item: solution_score(item, weights))[:max_solutions]
    rendered = []
    for selected in ranked:
        score = solution_score(selected, weights)
        rendered.append(
            {
                "course_ids": sorted(course["id"] for course in selected),
                "total_credits": round(sum(course["credits"] for course in selected), 4),
                "ranking": {
                    "campus_changes": score[0],
                    "active_days": score[1],
                    "gap_minutes": score[2],
                    "preference_weight": -score[3],
                },
            }
        )
    return {
        "schema": "yonsei-timetable-build/v1",
        "ok": True,
        "feasible": bool(rendered),
        "solutions": rendered,
        "searched_states": states,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "truncated": len(solutions) > max_solutions,
        "registration_mutation": "disabled",
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
