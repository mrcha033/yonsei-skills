#!/usr/bin/env python3
"""Prepare one Yonsei dorm action without submitting it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ACTIONS = {
    "status": (),
    "application": ("dorm", "term"),
    "payment": ("dorm", "term"),
    "roommate": ("dorm", "term", "reason"),
    "overnight": ("dorm", "date", "reason"),
    "repair": ("dorm", "location", "reason"),
    "facility_booking": ("dorm", "facility", "date", "time"),
    "move_in": ("dorm", "date"),
    "move_out": ("dorm", "date"),
}


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object.")
    action = str(payload.get("action", "")).strip().casefold()
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {sorted(ACTIONS)}.")
    missing = [field for field in ACTIONS[action] if not str(payload.get(field, "")).strip()]
    read_only = action == "status"
    return {
        "schema": "yonsei-dorm-action/v1",
        "action": action,
        "campus": payload.get("campus"),
        "dorm": payload.get("dorm"),
        "request": {
            field: payload.get(field)
            for field in ("term", "date", "time", "facility", "location", "reason")
            if payload.get(field) not in (None, "")
        },
        "official_status": payload.get("official_status"),
        "missing_fields": missing,
        "ready_for_confirmation": not read_only and not missing,
        "read_only": read_only,
        "action_performed": False,
        "next_step": (
            "report-visible-status"
            if read_only
            else "collect-missing-fields"
            if missing
            else "review-official-form-then-confirm"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
        output, code = run(payload), 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        output, code = {"schema": "yonsei-dorm-action-error/v1", "error": str(exc)}, 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
