#!/usr/bin/env python3
"""Check a user-supplied, privacy-minimized RMS participant snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-rms-participant-check/v1"
ERROR_SCHEMA = "yonsei-rms-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password", "passwd", "userpw", "otp", "token", "access_token",
    "refresh_token", "cookie", "cookies", "session", "sessionid",
    "name", "full_name", "email", "phone", "phone_number", "student_id",
    "employee_id", "researcher_id", "resident_registration_number", "rrn",
    "bank_account", "account_number", "tax_id",
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_sensitive(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "sensitive-field-not-allowed",
                    "Credential or direct-identifier fields are not accepted.",
                    f"{path}.{key}",
                )
            scan_sensitive(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_sensitive(item, f"{path}[{index}]")


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "A non-empty text value is required.", path)
    return value.strip()


def optional_text(value: Any, path: str) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise InputError("invalid-text", "Expected text or null.", path)
    return value.strip() or None


def parse_date(value: Any, path: str) -> date:
    text = required_text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise InputError("invalid-date", "Use an ISO date in YYYY-MM-DD form.", path) from exc


def allocation_value(value: Any, path: str) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise InputError(
            "invalid-allocation",
            "allocation_percent must be a number or decimal string.",
            path,
        )
    try:
        allocation = Decimal(str(value))
    except InvalidOperation as exc:
        raise InputError(
            "invalid-allocation",
            "allocation_percent is not a finite decimal.",
            path,
        ) from exc
    if not allocation.is_finite() or not Decimal(0) <= allocation <= Decimal(100):
        raise InputError(
            "invalid-allocation",
            "allocation_percent must be between 0 and 100.",
            path,
        )
    return allocation


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def transform(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise InputError("invalid-root", "Input must be a JSON object.")
    scan_sensitive(data)
    captured_at = required_text(data.get("captured_at"), "$.captured_at")
    project_code = required_text(data.get("project_code"), "$.project_code")
    source_format = data.get("source_format", "json")
    if source_format not in {"json", "excel-transcribed"}:
        raise InputError(
            "unsupported-source-format",
            "source_format must be json or excel-transcribed.",
            "$.source_format",
        )
    project_period = data.get("project_period")
    if not isinstance(project_period, dict):
        raise InputError(
            "invalid-project-period",
            "project_period must be an object.",
            "$.project_period",
        )
    project_start = parse_date(
        project_period.get("start_date"), "$.project_period.start_date"
    )
    project_end = parse_date(
        project_period.get("end_date"), "$.project_period.end_date"
    )
    if project_end < project_start:
        raise InputError(
            "invalid-project-period",
            "Project end_date must not be before start_date.",
            "$.project_period",
        )
    raw_participants = data.get("participants")
    if not isinstance(raw_participants, list):
        raise InputError(
            "invalid-participants",
            "participants must be an array.",
            "$.participants",
        )

    assignments = []
    issues = []
    unknowns = []
    duplicate_keys = set()
    events_by_participant = {}
    for index, raw in enumerate(raw_participants):
        path = f"$.participants[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-participant", "Each participant must be an object.", path)
        participant_key = required_text(
            raw.get("participant_key"), f"{path}.participant_key"
        )
        role = required_text(raw.get("role"), f"{path}.role")
        status = optional_text(raw.get("status"), f"{path}.status")
        start = parse_date(raw.get("start_date"), f"{path}.start_date")
        end = parse_date(raw.get("end_date"), f"{path}.end_date")
        if end < start:
            raise InputError(
                "invalid-participant-period",
                "Participant end_date must not be before start_date.",
                path,
            )
        if start < project_start or end > project_end:
            issues.append({
                "code": "assignment-outside-project-period",
                "participant_index": index,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            })
        duplicate_key = (participant_key.casefold(), role.casefold(), start, end)
        if duplicate_key in duplicate_keys:
            issues.append({
                "code": "duplicate-assignment",
                "participant_index": index,
            })
        duplicate_keys.add(duplicate_key)
        allocation = allocation_value(
            raw.get("allocation_percent"), f"{path}.allocation_percent"
        )
        if allocation is None:
            unknowns.append({
                "code": "missing-allocation",
                "participant_index": index,
            })
        else:
            events = events_by_participant.setdefault(participant_key, {})
            events[start] = events.get(start, Decimal(0)) + allocation
            day_after_end = end + timedelta(days=1)
            events[day_after_end] = events.get(day_after_end, Decimal(0)) - allocation
        assignments.append({
            "participant_ref": participant_key,
            "role": role,
            "status": status,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "allocation_percent": (
                decimal_text(allocation) if allocation is not None else None
            ),
        })

    for participant_key, events in sorted(events_by_participant.items()):
        active = Decimal(0)
        for event_date, delta in sorted(events.items()):
            active += delta
            if active > Decimal(100):
                issues.append({
                    "code": "overlapping-allocation-over-100",
                    "participant_ref": participant_key,
                    "effective_date": event_date.isoformat(),
                    "allocation_percent": decimal_text(active),
                })

    return {
        "schema": OUTPUT_SCHEMA,
        "provenance": {
            "mode": "user-supplied-snapshot",
            "source_format": source_format,
            "captured_at": captured_at,
            "live_system_queried": False,
        },
        "project_code": project_code,
        "project_period": {
            "start_date": project_start.isoformat(),
            "end_date": project_end.isoformat(),
        },
        "assignments": assignments,
        "issues": issues,
        "unknowns": unknowns,
        "complete": not issues and not unknowns,
        "writes_performed": False,
        "submitted": False,
    }


def load_input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_float=Decimal, parse_constant=reject_json_constant)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="JSON path or - for stdin")
    args = parser.parse_args()
    try:
        result = transform(load_input(args.input))
    except (InputError, json.JSONDecodeError, OSError, OverflowError) as exc:
        print(json.dumps({
            "schema": ERROR_SCHEMA,
            "error": {
                "code": getattr(exc, "code", "invalid-input"),
                "message": str(exc),
                "path": getattr(exc, "path", "$"),
            },
            "live_system_queried": False,
            "writes_performed": False,
            "submitted": False,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
