#!/usr/bin/env python3
"""Build an advisory semester plan for remaining Yonsei requirements."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_constant(value: str) -> None:
    raise InputError("invalid-json-number", f"Non-finite number is not allowed: {value}.")


def text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "Expected a non-empty string.", path)
    return value.strip()


def credits(value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise InputError("invalid-credits", "Expected non-negative credits.", path)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError("invalid-credits", "Expected non-negative credits.", path) from exc
    if not math.isfinite(result) or result < 0:
        raise InputError("invalid-credits", "Expected finite non-negative credits.", path)
    return result


def string_set(value: Any, path: str) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise InputError("invalid-string-list", "Expected an array of strings.", path)
    return {item.strip() for item in value if item.strip()}


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be an object.")
    progress = payload.get("progress")
    if not isinstance(progress, dict) or progress.get("schema") != "yonsei-graduation-progress/v1":
        raise InputError("invalid-progress", "progress must be yonsei-graduation-progress/v1.", "$.progress")

    terms_raw = payload.get("terms")
    if not isinstance(terms_raw, list) or not terms_raw:
        raise InputError("invalid-terms", "terms must be a non-empty array.", "$.terms")
    terms = [text(item, f"$.terms[{index}]") for index, item in enumerate(terms_raw)]
    if len(terms) != len(set(terms)):
        raise InputError("duplicate-term", "terms must be unique.", "$.terms")
    maximum = credits(payload.get("max_credits_per_term", 18), "$.max_credits_per_term")
    completed = string_set(payload.get("completed_course_codes"), "$.completed_course_codes")

    remaining_ids = {
        item["id"]
        for item in progress.get("requirements", [])
        if isinstance(item, dict) and not item.get("satisfied", False)
    }
    candidates_raw = payload.get("courses")
    if not isinstance(candidates_raw, list):
        raise InputError("invalid-courses", "courses must be an array.", "$.courses")
    courses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(candidates_raw):
        path = f"$.courses[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-course", "Each course must be an object.", path)
        code = text(raw.get("course_code"), f"{path}.course_code").upper()
        if code in seen:
            raise InputError("duplicate-course", f"Duplicate course: {code}.", path)
        seen.add(code)
        priority = raw.get("priority", 3)
        if not isinstance(priority, int) or isinstance(priority, bool) or not 1 <= priority <= 5:
            raise InputError("invalid-priority", "priority must be an integer from 1 to 5.", f"{path}.priority")
        courses.append(
            {
                "course_code": code,
                "title": raw.get("title"),
                "credits": credits(raw.get("credits"), f"{path}.credits"),
                "requirement_ids": string_set(raw.get("requirement_ids"), f"{path}.requirement_ids"),
                "prerequisites": {item.upper() for item in string_set(raw.get("prerequisites"), f"{path}.prerequisites")},
                "offered_terms": string_set(raw.get("offered_terms"), f"{path}.offered_terms"),
                "priority": priority,
                "required": bool(raw.get("required", False)),
            }
        )

    planned: set[str] = set(completed)
    covered: set[str] = set()
    schedule: list[dict[str, Any]] = []
    for term in terms:
        target_courses = [
            course
            for course in courses
            if course["course_code"] not in planned
            and bool(course["requirement_ids"] & (remaining_ids - covered))
        ]
        needed_prerequisites = set().union(
            *(course["prerequisites"] - planned for course in target_courses)
        ) if target_courses else set()
        available = [
            course
            for course in courses
            if course["course_code"] not in planned
            and (not course["offered_terms"] or term in course["offered_terms"])
            and course["prerequisites"].issubset(planned)
            and (
                bool(course["requirement_ids"] & (remaining_ids - covered))
                or course["course_code"] in needed_prerequisites
            )
        ]
        available.sort(
            key=lambda item: (
                item["course_code"] not in needed_prerequisites,
                not item["required"],
                -len(item["requirement_ids"] & (remaining_ids - covered)),
                -item["priority"],
                item["course_code"],
            )
        )
        selected: list[dict[str, Any]] = []
        term_credits = 0.0
        for course in available:
            if term_credits + course["credits"] > maximum:
                continue
            newly_covered = course["requirement_ids"] & (remaining_ids - covered)
            is_needed_prerequisite = course["course_code"] in needed_prerequisites
            if not newly_covered and not is_needed_prerequisite:
                continue
            selected.append(
                {
                    "course_code": course["course_code"],
                    "title": course["title"],
                    "credits": course["credits"],
                    "covers": sorted(newly_covered),
                    "prerequisite_for_later_requirement": is_needed_prerequisite,
                }
            )
            term_credits += course["credits"]
            planned.add(course["course_code"])
            covered.update(newly_covered)
        schedule.append(
            {
                "term": term,
                "credits": round(term_credits, 3),
                "courses": selected,
            }
        )
        if remaining_ids.issubset(covered):
            break

    unresolved = sorted(remaining_ids - covered)
    blockers: list[dict[str, Any]] = []
    for requirement_id in unresolved:
        mapped = [course for course in courses if requirement_id in course["requirement_ids"]]
        if not mapped:
            blockers.append({"requirement_id": requirement_id, "reason": "no-mapped-course"})
            continue
        unsatisfied_prerequisites = sorted(
            set().union(*(course["prerequisites"] - planned for course in mapped))
        )
        future_terms = sorted(set().union(*(course["offered_terms"] for course in mapped)))
        blockers.append(
            {
                "requirement_id": requirement_id,
                "reason": "not-scheduled",
                "unsatisfied_prerequisites": unsatisfied_prerequisites,
                "known_offered_terms": future_terms,
            }
        )

    return {
        "schema": "yonsei-graduation-path/v1",
        "advisory_only": True,
        "feasible_with_supplied_courses": not unresolved,
        "planned_terms": schedule,
        "covered_requirement_ids": sorted(covered),
        "unresolved_requirement_ids": unresolved,
        "blockers": blockers,
        "future_offerings_verified": all(course["offered_terms"] for course in courses),
        "registration_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = (
            json.load(sys.stdin, parse_constant=reject_constant)
            if args.input == "-"
            else json.loads(Path(args.input).read_text(encoding="utf-8"), parse_constant=reject_constant)
        )
        output = run(payload)
        code = 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        output = {
            "schema": "yonsei-graduation-path-error/v1",
            "error": {
                "code": getattr(exc, "code", "invalid-input"),
                "message": str(exc),
                "path": getattr(exc, "path", "$"),
            },
        }
        code = 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
