#!/usr/bin/env python3
"""Prepare an unsent Yonsei space reservation request."""

from __future__ import annotations

import argparse
import json
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
    pass


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("input must be an object")
    missing = [
        field
        for field in REQUIRED
        if field not in payload or payload[field] is None or payload[field] == ""
    ]
    headcount = payload.get("headcount")
    invalid: list[dict[str, str]] = []
    if headcount is not None and (
        not isinstance(headcount, int) or isinstance(headcount, bool) or headcount <= 0
    ):
        invalid.append({"field": "headcount", "message": "Must be a positive integer."})
    rule_report = payload.get("rule_report")
    if rule_report is None:
        missing.append("rule_report")
    elif not isinstance(rule_report, dict) or rule_report.get("schema") != "yonsei-space-rule-report/v1":
        invalid.append({"field": "rule_report", "message": "Expected yonsei-space-rule-report/v1."})
    elif rule_report.get("eligible") is not True:
        invalid.append({"field": "rule_report", "message": "Rule verdict is not an unqualified pass."})
    draft = {field: payload.get(field) for field in REQUIRED}
    draft["equipment"] = payload.get("equipment", [])
    draft["notes"] = payload.get("notes")
    ready = not missing and not invalid
    return {
        "schema": "yonsei-space-request-draft/v1",
        "ready_for_user_review": ready,
        "missing_fields": sorted(set(missing)),
        "invalid_fields": invalid,
        "draft": draft,
        "review_checklist": [
            "room-and-time-match-official-screen",
            "capacity-covers-headcount",
            "purpose-and-equipment-are-accurate",
            "fees-and-approval-process-understood",
            "user-confirms-before-any-future-submission",
        ],
        "submission_performed": False,
        "approval_status": "not-requested",
    }


def configure_utf8_stdio() -> None:
    """Keep Korean reservation requests lossless on every desktop OS."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
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
        print(json.dumps({"error": "invalid-input", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
