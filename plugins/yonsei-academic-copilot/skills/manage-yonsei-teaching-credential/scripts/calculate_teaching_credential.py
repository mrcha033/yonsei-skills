#!/usr/bin/env python3
"""Calculate advisory progress for a Yonsei teaching credential."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


STATUSES = {"completed", "in_progress", "scheduled", "missing", "unknown"}


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("requirements"), list):
        raise ValueError("Expected an object with a requirements array.")
    grouped = {status: [] for status in STATUSES}
    for raw in payload["requirements"]:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            raise ValueError("Each requirement requires a name.")
        status = str(raw.get("status", "unknown")).strip().casefold()
        if status not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}.")
        grouped[status].append(
            {
                "name": str(raw["name"]).strip(),
                "required": raw.get("required"),
                "completed": raw.get("completed"),
                "deadline": raw.get("deadline"),
                "source": raw.get("source"),
                "note": raw.get("note"),
            }
        )
    complete = bool(grouped["completed"]) and not any(
        grouped[status] for status in ("in_progress", "scheduled", "missing", "unknown")
    )
    dated = sorted(
        (
            item
            for status in ("in_progress", "scheduled", "missing")
            for item in grouped[status]
            if item.get("deadline")
        ),
        key=lambda item: item["deadline"],
    )
    return {
        "schema": "yonsei-teaching-credential-progress/v1",
        "profile": payload.get("profile", {}),
        "requirements": {key: value for key, value in grouped.items() if value},
        "next_dated_action": dated[0] if dated else None,
        "advisory_complete": complete,
        "official_confirmation_required": True,
        "official_diagnosis_triggered": False,
        "application_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
        output, code = run(payload), 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        output, code = {"schema": "yonsei-teaching-credential-error/v1", "error": str(exc)}, 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
