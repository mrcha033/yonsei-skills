#!/usr/bin/env python3
"""Shortlist exact official Yonsei shuttle rows for browser booking."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


AREA_CODES = {
    "s": "S",
    "i": "I",
    "sinchon": "S",
    "신촌": "S",
    "international": "I",
    "international-campus": "I",
    "송도": "I",
    "국제": "I",
    "국제캠퍼스": "I",
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def normalize_area(value: Any, path: str) -> str:
    if not isinstance(value, str) or value.strip().casefold() not in AREA_CODES:
        raise InputError("invalid-campus", "Use Sinchon or International Campus.", path)
    return AREA_CODES[value.strip().casefold()]


def normalize_date(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise InputError("invalid-date", "Expected YYYY-MM-DD or YYYYMMDD.", path)
    result = value.strip().replace("-", "").replace(".", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", result):
        raise InputError("invalid-date", "Expected YYYY-MM-DD or YYYYMMDD.", path)
    return result


def normalize_time(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise InputError("invalid-time", "Expected HH:MM or HHMM.", path)
    result = value.strip().replace(":", "")
    if not re.fullmatch(r"\d{4}", result):
        raise InputError("invalid-time", "Expected HH:MM or HHMM.", path)
    hour, minute = int(result[:2]), int(result[2:])
    if hour > 23 or minute > 59:
        raise InputError("invalid-time", "Time is out of range.", path)
    return result


def optional_time(value: Any, path: str) -> str | None:
    return None if value in (None, "") else normalize_time(value, path)


def nonnegative(value: Any, path: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise InputError("invalid-count", "Expected a non-negative integer.", path)
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise InputError("invalid-count", "Expected a non-negative integer.", path) from exc
    if result < 0:
        raise InputError("invalid-count", "Expected a non-negative integer.", path)
    return result


def flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    normalized = str(value).strip().casefold()
    if normalized in {"y", "yes", "true", "1", "가능", "예약신청"}:
        return True
    if normalized in {"n", "no", "false", "0", "불가", "마감"}:
        return False
    return None


def selector(row: dict[str, Any]) -> str:
    raw = "|".join(
        str(row[field]) for field in ("area_code", "bus_code", "date", "departure_time")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be an object.")
    query = payload.get("query")
    rows = payload.get("trips")
    if not isinstance(query, dict) or not isinstance(rows, list):
        raise InputError("invalid-input", "Expected query object and trips array.")
    origin = normalize_area(query.get("origin"), "$.query.origin")
    destination = normalize_area(query.get("destination"), "$.query.destination")
    if origin == destination:
        raise InputError("same-campus", "origin and destination must differ.", "$.query")
    date = normalize_date(query.get("date"), "$.query.date")
    after = optional_time(query.get("depart_after"), "$.query.depart_after")
    before = optional_time(query.get("depart_before"), "$.query.depart_before")
    preferred = optional_time(query.get("preferred_time"), "$.query.preferred_time")
    if after and before and after > before:
        raise InputError("invalid-window", "depart_after cannot exceed depart_before.", "$.query")
    allow_waitlist = bool(query.get("allow_waitlist", False))

    candidates: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        path = f"$.trips[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-trip", "Each trip must be an object.", path)
        area = normalize_area(str(raw.get("areaDivCd", raw.get("area_code", ""))), f"{path}.areaDivCd")
        bus_code = str(raw.get("busCd", raw.get("bus_code", ""))).strip()
        if not bus_code:
            raise InputError("missing-bus-code", "Official bus code is required.", f"{path}.busCd")
        trip_date = normalize_date(raw.get("stdrDt", raw.get("date")), f"{path}.stdrDt")
        start = normalize_time(raw.get("beginTm", raw.get("departure_time")), f"{path}.beginTm")
        end = optional_time(raw.get("endTm", raw.get("arrival_time")), f"{path}.endTm")
        remaining = nonnegative(raw.get("remndSeat", raw.get("remaining_seats")), f"{path}.remndSeat")
        reserve_allowed = flag(raw.get("resveYn", raw.get("reservation_allowed")))
        wait_allowed = flag(raw.get("resveWaitYn", raw.get("waitlist_allowed")))
        if area != origin or trip_date != date:
            continue
        if after and start < after:
            continue
        if before and start > before:
            continue
        mode = (
            "reserve"
            if remaining is not None and remaining > 0 and reserve_allowed is True
            else "waitlist"
            if allow_waitlist and wait_allowed is True
            else "unavailable"
        )
        if mode == "unavailable":
            continue
        normalized = {
            "area_code": area,
            "bus_code": bus_code,
            "bus_name": raw.get("busNm", raw.get("bus_name")),
            "date": trip_date,
            "departure_time": start,
            "arrival_time": end,
            "route": raw.get("thrstNm", raw.get("route")),
            "remaining_seats": remaining,
            "waitlist_count": nonnegative(
                raw.get("resveWaitPcnt", raw.get("waitlist_count")),
                f"{path}.resveWaitPcnt",
            ),
            "mode": mode,
        }
        normalized["selector"] = selector(normalized)
        target = int(preferred or after or "0000")
        actual = int(start)
        normalized["_distance"] = abs((actual // 100) * 60 + actual % 100 - ((target // 100) * 60 + target % 100))
        candidates.append(normalized)

    candidates.sort(
        key=lambda item: (
            item["mode"] != "reserve",
            item["_distance"],
            item["departure_time"],
            item["bus_code"],
        )
    )
    for item in candidates:
        item.pop("_distance")
    return {
        "schema": "yonsei-shuttle-booking-shortlist/v1",
        "query": {
            "origin_area_code": origin,
            "destination_area_code": destination,
            "date": date,
            "depart_after": after,
            "depart_before": before,
            "preferred_time": preferred,
            "allow_waitlist": allow_waitlist,
        },
        "candidate_count": len(candidates),
        "candidates": candidates[:5],
        "source_scope": "authenticated-official-browser-rows",
        "reservation_performed": False,
        "next_step": "recheck-selector-then-confirm",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8"))
        output = run(payload)
        code = 0
    except (OSError, json.JSONDecodeError, InputError) as exc:
        output = {
            "schema": "yonsei-shuttle-booking-error/v1",
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
