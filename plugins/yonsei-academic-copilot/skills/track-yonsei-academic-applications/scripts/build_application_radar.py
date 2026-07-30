#!/usr/bin/env python3
"""Build a read-only radar from authorized Yonsei academic-application rows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("applications"), list):
        raise ValueError("Expected an object with an applications array.")
    now = parse_time(payload.get("now")) or datetime.now().astimezone()
    sections = {"apply_now": [], "closing_soon": [], "in_progress": [], "needs_review": []}
    for raw in payload["applications"]:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            raise ValueError("Each application requires a name.")
        opens = parse_time(raw.get("opens_at"))
        closes = parse_time(raw.get("closes_at"))
        missing = [str(item).strip() for item in raw.get("missing_items", []) if str(item).strip()]
        status = str(raw.get("status", "")).strip().casefold()
        item = {
            "name": str(raw["name"]).strip(),
            "category": raw.get("category"),
            "opens_at": opens.isoformat() if opens else None,
            "closes_at": closes.isoformat() if closes else None,
            "status": raw.get("status"),
            "eligible": raw.get("eligible"),
            "missing_items": missing,
            "source": raw.get("source"),
        }
        if status in {"submitted", "received", "reviewing", "approved", "rejected", "제출", "접수", "심사중", "승인", "반려"}:
            section = "in_progress"
            action = "check-official-status"
        elif raw.get("eligible") is None or missing or not closes:
            section = "needs_review"
            action = "confirm-eligibility-or-missing-items"
        elif opens and now < opens:
            continue
        elif closes < now:
            continue
        elif closes <= now + timedelta(days=3):
            section = "closing_soon"
            action = "prepare-before-deadline"
        else:
            section = "apply_now"
            action = "review-application"
        item["next_action"] = action
        sections[section].append(item)
    for values in sections.values():
        values.sort(key=lambda item: item["closes_at"] or "9999")
    return {
        "schema": "yonsei-academic-application-radar/v1",
        "observed_at": now.isoformat(),
        "sections": {key: value for key, value in sections.items() if value},
        "submission_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
        output, code = run(payload), 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        output, code = {"schema": "yonsei-academic-application-error/v1", "error": str(exc)}, 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
