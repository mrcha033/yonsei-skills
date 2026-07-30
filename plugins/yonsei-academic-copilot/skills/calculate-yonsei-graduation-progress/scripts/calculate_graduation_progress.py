#!/usr/bin/env python3
"""Calculate advisory Yonsei graduation progress from explicit rules."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


STATUSES = {"completed", "in_progress", "failed", "withdrawn"}
RULE_TYPES = {"total_credits", "category_credits", "course_set", "fact"}


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


def number(value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise InputError("invalid-number", "Expected a non-negative number.", path)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError("invalid-number", "Expected a non-negative number.", path) from exc
    if not math.isfinite(result) or result < 0:
        raise InputError("invalid-number", "Expected a finite non-negative number.", path)
    return result


def official_url(value: Any, path: str) -> str:
    result = text(value, path)
    parsed = urlsplit(result)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "yonsei.ac.kr" or host.endswith(".yonsei.ac.kr")):
        raise InputError(
            "non-official-source",
            "Graduation-rule sources must use an official HTTPS yonsei.ac.kr host.",
            path,
        )
    return result


def normalize_course(raw: Any, index: int) -> dict[str, Any]:
    path = f"$.courses[{index}]"
    if not isinstance(raw, dict):
        raise InputError("invalid-course", "Each course must be an object.", path)
    code = text(raw.get("course_code"), f"{path}.course_code").upper()
    status = text(raw.get("status"), f"{path}.status").lower()
    if status not in STATUSES:
        raise InputError("invalid-status", f"status must be one of {sorted(STATUSES)}.", f"{path}.status")
    categories = raw.get("categories", [])
    if not isinstance(categories, list) or any(not isinstance(item, str) for item in categories):
        raise InputError("invalid-categories", "categories must be an array of strings.", f"{path}.categories")
    return {
        "course_code": code,
        "title": raw.get("title"),
        "credits": number(raw.get("credits"), f"{path}.credits"),
        "status": status,
        "categories": sorted({item.strip() for item in categories if item.strip()}),
    }


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be an object.")
    profile = payload.get("profile")
    if not isinstance(profile, dict):
        raise InputError("missing-profile", "profile must be an object.", "$.profile")
    required_profile = ("campus", "college", "major", "admission_year")
    normalized_profile = {
        key: text(profile.get(key), f"$.profile.{key}") for key in required_profile
    }

    sources_raw = payload.get("sources", [])
    if not isinstance(sources_raw, list):
        raise InputError("invalid-sources", "sources must be an array.", "$.sources")
    sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources_raw):
        path = f"$.sources[{index}]"
        if not isinstance(source, dict):
            raise InputError("invalid-source", "Each source must be an object.", path)
        source_id = text(source.get("id"), f"{path}.id")
        if source_id in sources:
            raise InputError("duplicate-source", f"Duplicate source id: {source_id}.", path)
        sources[source_id] = {
            "id": source_id,
            "url": official_url(source.get("url"), f"{path}.url"),
            "checked_on": text(source.get("checked_on"), f"{path}.checked_on"),
            "title": source.get("title"),
        }

    courses_raw = payload.get("courses")
    if not isinstance(courses_raw, list):
        raise InputError("invalid-courses", "courses must be an array.", "$.courses")
    courses = [normalize_course(raw, index) for index, raw in enumerate(courses_raw)]
    seen_codes: set[str] = set()
    for index, course in enumerate(courses):
        code = course["course_code"]
        if code in seen_codes and course["status"] in {"completed", "in_progress"}:
            raise InputError(
                "duplicate-active-course",
                "Repeated courses require an explicit resolved transcript row.",
                f"$.courses[{index}]",
            )
        if course["status"] in {"completed", "in_progress"}:
            seen_codes.add(code)

    requirements_raw = payload.get("requirements")
    if not isinstance(requirements_raw, list) or not requirements_raw:
        raise InputError("invalid-requirements", "requirements must be a non-empty array.", "$.requirements")
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        raise InputError("invalid-facts", "facts must be an object.", "$.facts")

    completed = [item for item in courses if item["status"] == "completed"]
    in_progress = [item for item in courses if item["status"] == "in_progress"]
    used_non_overlap: set[str] = set()
    reports: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    ids: set[str] = set()

    for index, raw in enumerate(requirements_raw):
        path = f"$.requirements[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-requirement", "Each requirement must be an object.", path)
        rule_id = text(raw.get("id"), f"{path}.id")
        if rule_id in ids:
            raise InputError("duplicate-requirement", f"Duplicate requirement id: {rule_id}.", path)
        ids.add(rule_id)
        label = text(raw.get("label"), f"{path}.label")
        rule_type = text(raw.get("type"), f"{path}.type")
        if rule_type not in RULE_TYPES:
            raise InputError("invalid-requirement-type", f"type must be one of {sorted(RULE_TYPES)}.", f"{path}.type")
        source_id = raw.get("source_id")
        source_verified = isinstance(source_id, str) and source_id in sources
        if not source_verified:
            unknowns.append({"type": "missing-official-source", "requirement_id": rule_id})

        report: dict[str, Any] = {
            "id": rule_id,
            "label": label,
            "type": rule_type,
            "source_id": source_id,
            "source_verified": source_verified,
        }
        if rule_type == "total_credits":
            minimum = number(raw.get("minimum"), f"{path}.minimum")
            earned = sum(item["credits"] for item in completed)
            projected = earned + sum(item["credits"] for item in in_progress)
            report.update(
                minimum=minimum,
                completed=round(earned, 3),
                in_progress=round(projected - earned, 3),
                remaining=round(max(0.0, minimum - earned), 3),
                projected_remaining=round(max(0.0, minimum - projected), 3),
                satisfied=earned >= minimum,
            )
        elif rule_type == "category_credits":
            category = text(raw.get("category"), f"{path}.category")
            minimum = number(raw.get("minimum"), f"{path}.minimum")
            allow_overlap = raw.get("allow_overlap", True)
            if not isinstance(allow_overlap, bool):
                raise InputError("invalid-overlap", "allow_overlap must be boolean.", f"{path}.allow_overlap")
            eligible_completed = [
                item for item in completed
                if category in item["categories"]
                and (allow_overlap or item["course_code"] not in used_non_overlap)
            ]
            eligible_in_progress = [
                item for item in in_progress
                if category in item["categories"]
                and (allow_overlap or item["course_code"] not in used_non_overlap)
            ]
            earned = sum(item["credits"] for item in eligible_completed)
            projected = earned + sum(item["credits"] for item in eligible_in_progress)
            if not allow_overlap:
                used_non_overlap.update(item["course_code"] for item in eligible_completed)
            report.update(
                category=category,
                minimum=minimum,
                allow_overlap=allow_overlap,
                completed=round(earned, 3),
                in_progress=round(projected - earned, 3),
                remaining=round(max(0.0, minimum - earned), 3),
                projected_remaining=round(max(0.0, minimum - projected), 3),
                matched_completed_courses=[item["course_code"] for item in eligible_completed],
                satisfied=earned >= minimum,
            )
        elif rule_type == "course_set":
            codes_raw = raw.get("course_codes")
            if not isinstance(codes_raw, list) or any(not isinstance(item, str) for item in codes_raw):
                raise InputError("invalid-course-set", "course_codes must be an array of strings.", f"{path}.course_codes")
            codes = {item.strip().upper() for item in codes_raw if item.strip()}
            minimum_count = raw.get("minimum_count", len(codes))
            if not isinstance(minimum_count, int) or isinstance(minimum_count, bool) or minimum_count < 0:
                raise InputError("invalid-count", "minimum_count must be a non-negative integer.", f"{path}.minimum_count")
            done = sorted(item["course_code"] for item in completed if item["course_code"] in codes)
            active = sorted(item["course_code"] for item in in_progress if item["course_code"] in codes)
            report.update(
                course_codes=sorted(codes),
                minimum_count=minimum_count,
                completed_count=len(done),
                in_progress_count=len(active),
                completed_courses=done,
                in_progress_courses=active,
                missing_courses=sorted(codes - set(done) - set(active)),
                remaining_count=max(0, minimum_count - len(done)),
                projected_remaining_count=max(0, minimum_count - len(done) - len(active)),
                satisfied=len(done) >= minimum_count,
            )
        else:
            key = text(raw.get("key"), f"{path}.key")
            expected = raw.get("expected", True)
            known = key in facts
            actual = facts.get(key)
            report.update(
                key=key,
                expected=expected,
                actual=actual,
                known=known,
                satisfied=known and actual == expected,
            )
            if not known:
                unknowns.append({"type": "missing-fact", "requirement_id": rule_id, "key": key})
        reports.append(report)

    complete = not unknowns and all(item["source_verified"] for item in reports)
    satisfied = complete and all(item["satisfied"] for item in reports)
    return {
        "schema": "yonsei-graduation-progress/v1",
        "profile": normalized_profile,
        "official_audit": False,
        "advisory_only": True,
        "complete": complete,
        "all_requirements_satisfied": satisfied,
        "requirements": reports,
        "unknowns": unknowns,
        "sources": list(sources.values()),
        "next_action": (
            "confirm-with-official-graduation-audit"
            if satisfied
            else "plan-remaining-requirements"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        if args.input == "-":
            payload = json.load(sys.stdin, parse_constant=reject_constant)
        else:
            payload = json.loads(Path(args.input).read_text(encoding="utf-8"), parse_constant=reject_constant)
        output = run(payload)
        code = 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        output = {
            "schema": "yonsei-graduation-error/v1",
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
