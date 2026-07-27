#!/usr/bin/env python3
"""Check one proposed booking against published Yonsei space rules."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


SOURCE = "https://space.yonsei.ac.kr/ys_popform.php?mid=K00_01"
APPLICANTS = {
    "student",
    "graduate_student",
    "staff",
    "alumni",
    "registered_organization",
    "general_public",
}


class InputError(ValueError):
    def __init__(self, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.path = path


def parse_date(value: Any, path: str) -> dt.date:
    if not isinstance(value, str):
        raise InputError("Expected YYYY-MM-DD.", path)
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise InputError("Expected YYYY-MM-DD.", path) from exc


def parse_datetime(value: Any, path: str) -> dt.datetime:
    if not isinstance(value, str):
        raise InputError("Expected an ISO 8601 timestamp.", path)
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise InputError("Expected an ISO 8601 timestamp.", path) from exc


def parse_clock(value: Any, path: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}:\d{2}", value.strip()):
        raise InputError("Expected HH:MM.", path)
    hour, minute = (int(part) for part in value.split(":"))
    if hour > 23 or minute > 59:
        raise InputError("Clock value is out of range.", path)
    return hour * 60 + minute


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("Input must be an object.")
    requested_at = parse_datetime(payload.get("requested_on"), "$.requested_on")
    booking_date = parse_date(payload.get("date"), "$.date")
    start = parse_clock(payload.get("start"), "$.start")
    end = parse_clock(payload.get("end"), "$.end")
    if end <= start:
        raise InputError("end must be after start.", "$.end")
    applicant = payload.get("applicant_type")
    if applicant not in APPLICANTS:
        raise InputError(
            f"applicant_type must be one of {sorted(APPLICANTS)}.", "$.applicant_type"
        )
    bookings = payload.get("bookings_in_same_7_day_window")
    if not isinstance(bookings, int) or isinstance(bookings, bool) or bookings < 0:
        raise InputError(
            "bookings_in_same_7_day_window must be a non-negative integer.",
            "$.bookings_in_same_7_day_window",
        )
    restricted = payload.get("restricted_period")
    if not (
        restricted is True
        or restricted is False
        or restricted is None
        or restricted == "unknown"
    ):
        raise InputError("restricted_period must be true, false, or unknown.", "$.restricted_period")

    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    lead_days = (booking_date - requested_at.date()).days
    duration = end - start

    def violation(rule: str, message: str, **details: Any) -> None:
        violations.append({"rule": rule, "message": message, "source": SOURCE, **details})

    if lead_days < 1:
        violation("at-least-one-day-ahead", "Same-day or past booking requests are not allowed.", lead_days=lead_days)
    if lead_days > 14:
        violation("maximum-fourteen-days-ahead", "The requested date is more than 14 days ahead.", lead_days=lead_days)
    if duration > 240:
        violation("maximum-four-hours", "One booking may not exceed four hours.", duration_minutes=duration)
    if start % 10 or end % 10:
        violation("ten-minute-interval", "Start and end must use ten-minute intervals.")
    if bookings >= 2:
        violation(
            "maximum-two-in-seven-days",
            "Two bookings already exist in the same seven-day window.",
            existing_bookings=bookings,
        )
    if restricted is True:
        violation(
            "restricted-period",
            "The requested date is marked as an opening-week, exam, or special-event restricted period.",
        )
    elif restricted in {None, "unknown"}:
        unknowns.append(
            {
                "rule": "restricted-period",
                "message": "Confirm that the date is not in an opening-week, exam, or special-event restriction.",
                "source": SOURCE,
            }
        )
    if (
        requested_at.weekday() < 5
        and (requested_at.hour > 16 or (requested_at.hour == 16 and requested_at.minute > 0))
    ):
        warnings.append(
            {
                "rule": "weekday-approval-cutoff",
                "message": "The public guide says weekday approvals are not processed after 16:00.",
                "source": SOURCE,
            }
        )
    if applicant == "general_public":
        warnings.append(
            {
                "rule": "general-public-registration-and-fees",
                "message": "General-public use requires organization registration and may require a fee.",
                "source": "https://space.yonsei.ac.kr/ys_popform.php?mid=K00_06",
            }
        )
    eligible: bool | None = False if violations else (None if unknowns else True)
    return {
        "schema": "yonsei-space-rule-report/v1",
        "policy_as_of": "2026-07-27",
        "eligible": eligible,
        "lead_days": lead_days,
        "duration_minutes": duration,
        "violations": violations,
        "unknowns": unknowns,
        "warnings": warnings,
        "workflow_reminders": [
            "staff-approval-required",
            "payment-required-if-paid-space",
            "approval-message-or-permit-required-before-use",
        ],
        "submission_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                run(json.loads(args.input.read_text(encoding="utf-8"))),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(
            json.dumps(
                {"error": "invalid-input", "message": str(exc), "path": getattr(exc, "path", "$")},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
