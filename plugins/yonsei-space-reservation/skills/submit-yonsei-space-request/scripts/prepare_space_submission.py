#!/usr/bin/env python3
"""Prepare an exact, reviewed Yonsei space application for browser submission."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED = (
    "applicant_type",
    "organizer",
    "contact",
    "space_id",
    "space_name",
    "date",
    "start",
    "end",
    "headcount",
    "purpose",
)


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-field", "Expected a non-empty string.", path)
    return value.strip()


def clock(value: Any, path: str) -> str:
    result = text(value, path)
    if not re.fullmatch(r"\d{1,2}:\d{2}", result):
        raise InputError("invalid-time", "Expected HH:MM.", path)
    hour, minute = (int(part) for part in result.split(":"))
    if hour > 23 or minute > 59:
        raise InputError("invalid-time", "Time is out of range.", path)
    return f"{hour:02d}:{minute:02d}"


def optional_fee(value: Any, path: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise InputError("invalid-fee", "Expected a non-negative fee.", path)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError("invalid-fee", "Expected a non-negative fee.", path) from exc
    if not math.isfinite(result) or result < 0:
        raise InputError("invalid-fee", "Expected a finite non-negative fee.", path)
    return result


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be an object.")
    request = payload.get("request")
    selected = payload.get("selected_space")
    rule_report = payload.get("rule_report")
    draft_report = payload.get("draft_report")
    if not isinstance(request, dict) or not isinstance(selected, dict):
        raise InputError("invalid-input", "request and selected_space must be objects.")
    if not isinstance(rule_report, dict) or rule_report.get("schema") != "yonsei-space-rule-report/v1":
        raise InputError("invalid-rule-report", "Expected yonsei-space-rule-report/v1.", "$.rule_report")
    if rule_report.get("eligible") is not True:
        raise InputError("rule-check-not-passed", "The space rule report is not an unqualified pass.", "$.rule_report")
    if not isinstance(draft_report, dict) or draft_report.get("schema") != "yonsei-space-request-draft/v1":
        raise InputError("invalid-draft-report", "Expected yonsei-space-request-draft/v1.", "$.draft_report")
    if draft_report.get("ready_for_user_review") is not True:
        raise InputError("draft-not-ready", "The request draft is not ready for review.", "$.draft_report")

    normalized = {field: request.get(field) for field in REQUIRED}
    for field in REQUIRED:
        if field == "headcount":
            continue
        normalized[field] = text(normalized[field], f"$.request.{field}")
    headcount = request.get("headcount")
    if not isinstance(headcount, int) or isinstance(headcount, bool) or headcount <= 0:
        raise InputError("invalid-headcount", "headcount must be a positive integer.", "$.request.headcount")
    normalized["headcount"] = headcount
    normalized["start"] = clock(normalized["start"], "$.request.start")
    normalized["end"] = clock(normalized["end"], "$.request.end")
    if normalized["end"] <= normalized["start"]:
        raise InputError("invalid-time-range", "end must be after start.", "$.request.end")

    selected_id = text(selected.get("space_id"), "$.selected_space.space_id")
    if selected_id != normalized["space_id"]:
        raise InputError("space-mismatch", "The reviewed request and selected live space differ.", "$.selected_space.space_id")
    capacity = selected.get("capacity")
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        raise InputError("invalid-capacity", "selected_space.capacity must be a positive integer.", "$.selected_space.capacity")
    if capacity < headcount:
        raise InputError("capacity-too-small", "Selected space capacity is below headcount.", "$.selected_space.capacity")
    live_date = text(selected.get("date"), "$.selected_space.date")
    live_start = clock(selected.get("available_start"), "$.selected_space.available_start")
    live_end = clock(selected.get("available_end"), "$.selected_space.available_end")
    if live_date != normalized["date"] or not (live_start <= normalized["start"] < normalized["end"] <= live_end):
        raise InputError("availability-mismatch", "The requested interval is outside the selected live availability.")

    fee = optional_fee(selected.get("displayed_fee"), "$.selected_space.displayed_fee")
    fee_known = selected.get("displayed_fee") not in (None, "")
    snapshot = {
        "space_id": selected_id,
        "date": live_date,
        "start": normalized["start"],
        "end": normalized["end"],
        "headcount": headcount,
        "purpose": normalized["purpose"],
    }
    selector = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema": "yonsei-space-submission/v1",
        "ready_for_confirmation": fee_known,
        "selector": selector,
        "request": normalized,
        "selected_space": {
            "space_id": selected_id,
            "space_name": selected.get("space_name", normalized["space_name"]),
            "building": selected.get("building"),
            "capacity": capacity,
            "displayed_fee": fee,
            "fee_known": fee_known,
        },
        "confirmation_summary": {
            "space": selected.get("space_name", normalized["space_name"]),
            "date": normalized["date"],
            "time": f"{normalized['start']}–{normalized['end']}",
            "headcount": headcount,
            "purpose": normalized["purpose"],
            "displayed_fee": fee,
            "contact": normalized["contact"],
        },
        "submission_performed": False,
        "next_step": (
            "confirm-immediately-before-submit"
            if fee_known
            else "read-displayed-fee-or-free-status"
        ),
    }


def configure_utf8_stdio() -> None:
    """Keep Korean space requests and results lossless on every desktop OS."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8"))
        output = run(payload)
        code = 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        output = {
            "schema": "yonsei-space-submission-error/v1",
            "error": {
                "code": getattr(exc, "code", "invalid-input"),
                "message": str(exc),
                "path": getattr(exc, "path", "$"),
            },
        }
        code = 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
