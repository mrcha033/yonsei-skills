#!/usr/bin/env python3
"""Allocate Yonsei course-registration mileage with explicit uncertainty."""

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


def integer(value: Any, path: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise InputError("invalid-integer", f"Expected an integer >= {minimum}.", path)
    if maximum is not None and value > maximum:
        raise InputError("invalid-integer", f"Expected an integer <= {maximum}.", path)
    return value


def optional_integer(value: Any, path: str) -> int | None:
    if value in (None, ""):
        return None
    return integer(value, path)


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "Expected a non-empty string.", path)
    return value.strip()


def probability(bid: int, cutoff: float, scale: float) -> float:
    exponent = max(-60.0, min(60.0, -(bid - cutoff) / scale))
    return 1.0 / (1.0 + math.exp(exponent))


def history_result(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"success", "successful", "enrolled", "accepted", "y", "성공", "수강", "배정"}:
        return True
    if normalized in {"failed", "failure", "rejected", "n", "실패", "탈락", "미배정"}:
        return False
    return None


def matching_history(
    raw_history: list[Any],
    course: dict[str, Any],
    path: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_history):
        item_path = f"{path}[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-history-row", "Each history row must be an object.", item_path)
        row_course_id = str(raw.get("course_id", "")).strip()
        row_course_code = str(raw.get("course_code", "")).strip()
        same_course = bool(row_course_id and row_course_id == course["course_id"])
        same_code = bool(
            row_course_code
            and course["course_code"]
            and row_course_code.casefold() == str(course["course_code"]).strip().casefold()
        )
        if not (same_course or same_code):
            continue
        mileage = optional_integer(raw.get("mileage"), f"{item_path}.mileage")
        if mileage is None:
            continue
        matches.append(
            {
                "term": raw.get("term"),
                "course_id": row_course_id or None,
                "course_code": row_course_code or None,
                "section": raw.get("section"),
                "mileage": mileage,
                "successful": history_result(raw.get("successful", raw.get("status"))),
                "applied_course_count": optional_integer(
                    raw.get("applied_course_count"),
                    f"{item_path}.applied_course_count",
                ),
                "first_time": raw.get("first_time"),
                "major_status": raw.get("major_status"),
                "year": raw.get("year"),
                "earned_credit_ratio": raw.get("earned_credit_ratio"),
                "total_earned_credit_ratio": raw.get("total_earned_credit_ratio"),
                "graduation_context": raw.get("graduation_context"),
            }
        )
    return matches


def inferred_cutoff(course: dict[str, Any]) -> tuple[float, str]:
    if course["past_cutoff"] is not None:
        return float(course["past_cutoff"]), "past-cutoff"
    history = course["personal_history"]
    successes = [row["mileage"] for row in history if row["successful"] is True]
    failures = [row["mileage"] for row in history if row["successful"] is False]
    if successes and failures and max(failures) < min(successes):
        return (max(failures) + min(successes)) / 2, "personal-history-band"
    if successes:
        return float(min(successes)), "personal-success-observation"
    if failures:
        return float(min(course["mileage_cap"], max(failures) + 1)), "personal-failure-lower-bound"
    capacity = course["capacity"]
    applicants = course["applicants"]
    cap = course["mileage_cap"]
    if capacity is not None and applicants is not None and capacity > 0:
        ratio = applicants / capacity
        proxy = cap * max(0.08, min(0.82, (ratio - 0.65) / 2.2))
        return round(proxy, 2), "demand-proxy"
    return cap * 0.35, "unknown-demand-proxy"


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be an object.")
    total = integer(payload.get("total_mileage"), "$.total_mileage", maximum=500)
    raw_courses = payload.get("courses")
    if not isinstance(raw_courses, list) or not raw_courses:
        raise InputError("invalid-courses", "courses must be a non-empty array.", "$.courses")
    top_level_history = payload.get("underwood_history", [])
    if not isinstance(top_level_history, list):
        raise InputError(
            "invalid-history",
            "underwood_history must be an array.",
            "$.underwood_history",
        )

    courses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_courses):
        path = f"$.courses[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-course", "Each course must be an object.", path)
        course_id = required_text(raw.get("course_id"), f"{path}.course_id")
        if course_id in seen:
            raise InputError("duplicate-course", f"Duplicate course_id: {course_id}.", path)
        seen.add(course_id)
        cap = integer(raw.get("mileage_cap", total), f"{path}.mileage_cap")
        importance = integer(raw.get("importance", 3), f"{path}.importance", minimum=1, maximum=5)
        alternatives_raw = raw.get("alternatives", [])
        if not isinstance(alternatives_raw, list) or any(not isinstance(item, str) for item in alternatives_raw):
            raise InputError("invalid-alternatives", "alternatives must be an array of course IDs.", f"{path}.alternatives")
        course = {
            "course_id": course_id,
            "course_code": raw.get("course_code"),
            "title": raw.get("title"),
            "capacity": optional_integer(raw.get("capacity"), f"{path}.capacity"),
            "applicants": optional_integer(raw.get("applicants"), f"{path}.applicants"),
            "past_cutoff": optional_integer(raw.get("past_cutoff"), f"{path}.past_cutoff"),
            "mileage_cap": cap,
            "importance": importance,
            "required_for_graduation": bool(raw.get("required_for_graduation", False)),
            "alternatives": sorted({item.strip() for item in alternatives_raw if item.strip()}),
            "history_as_of": raw.get("history_as_of"),
        }
        local_history = raw.get("personal_history", [])
        if not isinstance(local_history, list):
            raise InputError(
                "invalid-history",
                "personal_history must be an array.",
                f"{path}.personal_history",
            )
        course["personal_history"] = matching_history(
            [*top_level_history, *local_history],
            course,
            "$.underwood_history",
        )
        cutoff, evidence = inferred_cutoff(course)
        course["estimated_cutoff"] = cutoff
        course["evidence"] = evidence
        courses.append(course)

    # Integer dynamic programming: maximize risk-adjusted expected course value.
    states: list[tuple[float, list[int]] | None] = [None] * (total + 1)
    states[0] = (0.0, [])
    for course in courses:
        next_states: list[tuple[float, list[int]] | None] = [None] * (total + 1)
        scale = max(1.5, course["mileage_cap"] * 0.08)
        base_value = float(course["importance"])
        if course["required_for_graduation"]:
            base_value += 3.0
        if not course["alternatives"]:
            base_value += 1.0
        for spent, state in enumerate(states):
            if state is None:
                continue
            for bid in range(0, min(course["mileage_cap"], total - spent) + 1):
                chance = probability(bid, course["estimated_cutoff"], scale)
                value = state[0] + base_value * chance - bid * 0.002
                candidate = (value, state[1] + [bid])
                slot = next_states[spent + bid]
                if slot is None or candidate[0] > slot[0]:
                    next_states[spent + bid] = candidate
        states = next_states

    best_spent, best_state = max(
        ((spent, state) for spent, state in enumerate(states) if state is not None),
        key=lambda item: (item[1][0], -item[0]),
    )
    bids = best_state[1]
    recommendations: list[dict[str, Any]] = []
    for course, bid in zip(courses, bids):
        scale = max(1.5, course["mileage_cap"] * 0.08)
        chance = probability(bid, course["estimated_cutoff"], scale)
        risk = "low" if chance >= 0.8 else "medium" if chance >= 0.5 else "high"
        missing = [
            field
            for field in ("capacity", "applicants", "past_cutoff")
            if course[field] is None
        ]
        recommendations.append(
            {
                "course_id": course["course_id"],
                "course_code": course["course_code"],
                "title": course["title"],
                "recommended_mileage": bid,
                "mileage_cap": course["mileage_cap"],
                "risk_band": risk,
                "planning_probability": round(chance, 3),
                "estimated_cutoff": course["estimated_cutoff"],
                "cutoff_basis": course["evidence"],
                "missing_evidence": missing,
                "required_for_graduation": course["required_for_graduation"],
                "alternatives": course["alternatives"],
                "history_as_of": course["history_as_of"],
                "personal_history_count": len(course["personal_history"]),
                "personal_history": course["personal_history"],
                "tie_break_context": [
                    {
                        key: row[key]
                        for key in (
                            "term",
                            "applied_course_count",
                            "first_time",
                            "major_status",
                            "year",
                            "earned_credit_ratio",
                            "total_earned_credit_ratio",
                            "graduation_context",
                        )
                        if row.get(key) not in (None, "")
                    }
                    for row in course["personal_history"]
                ],
            }
        )
    recommendations.sort(
        key=lambda item: (
            not item["required_for_graduation"],
            {"high": 0, "medium": 1, "low": 2}[item["risk_band"]],
            item["course_id"],
        )
    )
    return {
        "schema": "yonsei-mileage-strategy/v2",
        "total_mileage": total,
        "allocated_mileage": best_spent,
        "unallocated_mileage": total - best_spent,
        "recommendations": recommendations,
        "guaranteed": False,
        "assumptions": [
            "Past cutoffs and current demand are planning signals, not admission guarantees.",
            "Underwood mileage history is personal evidence, not a population cutoff.",
            "Major, year, earned-credit, first-time, and other same-mileage tie breakers are shown as context but are not converted into a guaranteed score.",
            "Recalculate after capacity, applicant counts, or the student's course set changes.",
        ],
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
            "schema": "yonsei-mileage-strategy-error/v1",
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
