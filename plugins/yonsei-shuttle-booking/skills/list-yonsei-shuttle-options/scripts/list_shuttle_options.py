#!/usr/bin/env python3
"""Normalize and filter user-supplied Yonsei shuttle rows."""

from __future__ import annotations

import argparse
import json
import re
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


def first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def date_value(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(".", "-").replace("/", "-")
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise InputError("invalid-date", "Expected YYYY-MM-DD or YYYYMMDD.", path)
    return text


def clock_value(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}", text):
        text = f"{text[:2]}:{text[2:]}"
    if not re.fullmatch(r"\d{1,2}:\d{2}", text):
        raise InputError("invalid-clock", "Expected HH:MM or HHMM.", path)
    hour, minute = (int(part) for part in text.split(":"))
    if hour > 23 or minute > 59:
        raise InputError("invalid-clock", "Clock value is out of range.", path)
    return f"{hour:02d}:{minute:02d}"


def int_value(value: Any, path: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise InputError("invalid-integer", "Expected a non-negative integer.", path)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InputError("invalid-integer", "Expected a non-negative integer.", path) from exc
    if number < 0:
        raise InputError("invalid-integer", "Expected a non-negative integer.", path)
    return number


def normalize(row: Any, index: int) -> dict[str, Any]:
    path = f"$.options[{index}]"
    if not isinstance(row, dict):
        raise InputError("invalid-option", "Each option must be an object.", path)
    bus_code = first(row, "busCd", "bus_code", "trip_id", "id")
    date = date_value(first(row, "stdrDt", "date", "departure_date"), f"{path}.date")
    start = clock_value(first(row, "beginTm", "departure_time", "start"), f"{path}.departure_time")
    end = clock_value(first(row, "endTm", "arrival_time", "end"), f"{path}.arrival_time")
    origin = first(row, "thrstNm", "origin", "departure_area", "area_name")
    destination = first(row, "destination", "arrival_area")
    remaining = int_value(
        first(row, "remndSeat", "remaining_seats", "seats_remaining"),
        f"{path}.remaining_seats",
    )
    return {
        "trip_id": str(bus_code) if bus_code not in (None, "") else f"row-{index + 1}",
        "bus_name": first(row, "busNm", "bus_name", "route_name"),
        "date": date,
        "departure_time": start,
        "arrival_time": end,
        "origin": str(origin) if origin not in (None, "") else None,
        "destination": str(destination) if destination not in (None, "") else None,
        "remaining_seats": remaining,
        "waitlist_count": int_value(
            first(row, "resveWaitPcnt", "waitlist_count"),
            f"{path}.waitlist_count",
        ),
        "reservation_flag": first(row, "resveYn", "reservation_allowed"),
        "waitlist_flag": first(row, "resveWaitYn", "waitlist_allowed"),
        "snapshot_row": index,
    }


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("options"), list):
        raise InputError("invalid-input", "Input must be an object with an options array.")
    filters = payload.get("filters", {})
    if not isinstance(filters, dict):
        raise InputError("invalid-filters", "filters must be an object.", "$.filters")
    wanted_date = date_value(filters.get("date"), "$.filters.date")
    after = clock_value(filters.get("depart_after"), "$.filters.depart_after")
    before = clock_value(filters.get("depart_before"), "$.filters.depart_before")
    minimum = int_value(
        filters.get("minimum_remaining_seats"), "$.filters.minimum_remaining_seats"
    )
    wanted_origin = str(filters.get("origin", "")).strip().casefold()
    wanted_destination = str(filters.get("destination", "")).strip().casefold()

    matches: list[dict[str, Any]] = []
    excluded_unknown: list[dict[str, Any]] = []
    for index, raw in enumerate(payload["options"]):
        option = normalize(raw, index)
        unknown: list[str] = []
        mismatch = False
        checks = [
            ("date", wanted_date, option["date"], lambda a, b: a == b),
            (
                "origin",
                wanted_origin or None,
                option["origin"].casefold() if option["origin"] else None,
                lambda a, b: a in b,
            ),
            (
                "destination",
                wanted_destination or None,
                option["destination"].casefold() if option["destination"] else None,
                lambda a, b: a in b,
            ),
        ]
        for field, wanted, actual, predicate in checks:
            if wanted is None:
                continue
            if actual is None:
                unknown.append(field)
            elif not predicate(wanted, actual):
                mismatch = True
        if after is not None:
            if option["departure_time"] is None:
                unknown.append("departure_time")
            elif option["departure_time"] < after:
                mismatch = True
        if before is not None:
            if option["departure_time"] is None:
                unknown.append("departure_time")
            elif option["departure_time"] > before:
                mismatch = True
        if minimum is not None:
            if option["remaining_seats"] is None:
                unknown.append("remaining_seats")
            elif option["remaining_seats"] < minimum:
                mismatch = True
        if unknown and not mismatch:
            excluded_unknown.append(
                {"trip_id": option["trip_id"], "missing_for_filters": sorted(set(unknown))}
            )
        elif not mismatch:
            matches.append(option)
    matches.sort(
        key=lambda row: (
            row["date"] or "9999-99-99",
            row["departure_time"] or "99:99",
            row["trip_id"],
        )
    )
    return {
        "schema": "yonsei-shuttle-options/v1",
        "source_scope": "user-supplied-snapshot",
        "live_availability": False,
        "input_count": len(payload["options"]),
        "matched_count": len(matches),
        "options": matches,
        "excluded_unknown": excluded_unknown,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(
            args.input.read_text(encoding="utf-8"), parse_constant=reject_constant
        )
        print(json.dumps(run(payload), ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        body = {
            "error": getattr(exc, "code", "invalid-input"),
            "message": str(exc),
            "path": getattr(exc, "path", "$"),
        }
        print(json.dumps(body, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
