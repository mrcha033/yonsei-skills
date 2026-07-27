#!/usr/bin/env python3
"""Classify one user-supplied Yonsei shuttle seat snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class InputError(ValueError):
    pass


def first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"y", "yes", "true", "1", "가능", "예약신청"}:
        return True
    if normalized in {"n", "no", "false", "0", "불가", "마감"}:
        return False
    return None


def remaining(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise InputError("remaining seats must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise InputError("remaining seats must be a non-negative integer") from exc
    if result < 0:
        raise InputError("remaining seats must be a non-negative integer")
    return result


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("trip"), dict):
        raise InputError("input must be an object with one trip object")
    trip = payload["trip"]
    seats = remaining(first(trip, "remndSeat", "remaining_seats", "seats_remaining"))
    reserve = flag(first(trip, "resveYn", "reservation_allowed"))
    waitlist = flag(first(trip, "resveWaitYn", "waitlist_allowed"))
    reasons: list[str] = []
    if seats is None:
        verdict = "unknown"
        reasons.append("remaining-seat-count-missing")
    elif seats > 0 and reserve is True:
        verdict = "seats-available"
    elif seats > 0 and reserve is False:
        verdict = "reservation-closed"
        reasons.append("seat-count-positive-but-reservation-flag-closed")
    elif seats > 0:
        verdict = "unknown"
        reasons.append("reservation-flag-missing")
    elif waitlist is True:
        verdict = "waitlist-only"
    elif waitlist is False and reserve is False:
        verdict = "sold-out"
    elif waitlist is False and reserve is True:
        verdict = "unknown"
        reasons.append("zero-seats-conflicts-with-reservation-flag")
    else:
        verdict = "unknown"
        reasons.append("waitlist-or-reservation-flags-missing")
    return {
        "schema": "yonsei-shuttle-seat-status/v1",
        "source_scope": "user-supplied-snapshot",
        "live_availability": False,
        "observed_at": payload.get("observed_at"),
        "trip": {
            "trip_id": first(trip, "busCd", "trip_id", "id"),
            "bus_name": first(trip, "busNm", "bus_name", "route_name"),
            "date": first(trip, "stdrDt", "date"),
            "departure_time": first(trip, "beginTm", "departure_time"),
        },
        "remaining_seats": seats,
        "reservation_allowed": reserve,
        "waitlist_allowed": waitlist,
        "verdict": verdict,
        "reasons": reasons,
        "reservation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(json.loads(args.input.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(json.dumps({"error": "invalid-input", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
