#!/usr/bin/env python3
"""Filter a user-supplied Yonsei space availability snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class InputError(ValueError):
    def __init__(self, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.path = path


def clock(value: Any, path: str) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", text):
        raise InputError("Expected HH:MM.", path)
    hour, minute = (int(part) for part in text.split(":"))
    if hour > 23 or minute > 59:
        raise InputError("Clock value is out of range.", path)
    return hour * 60 + minute


def nonnegative_int(value: Any, path: str) -> int | None:
    if value in (None, ""):
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputError("Expected a non-negative integer.", path)
    return value


def string_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise InputError("Expected an array of strings.", path)
    return sorted({item.strip().casefold() for item in value if item.strip()})


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("spaces"), list):
        raise InputError("Input must be an object with a spaces array.")
    query = payload.get("query", {})
    if not isinstance(query, dict):
        raise InputError("query must be an object.", "$.query")
    q_start = clock(query.get("start"), "$.query.start")
    q_end = clock(query.get("end"), "$.query.end")
    if (q_start is None) != (q_end is None):
        raise InputError("start and end must be supplied together.", "$.query")
    if q_start is not None and q_end <= q_start:
        raise InputError("end must be after start.", "$.query")
    minimum = nonnegative_int(query.get("minimum_capacity"), "$.query.minimum_capacity")
    required = set(string_list(query.get("required_equipment"), "$.query.required_equipment"))
    wanted_date = query.get("date")
    wanted_building = str(query.get("building", "")).strip().casefold()

    matches: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    for index, row in enumerate(payload["spaces"]):
        path = f"$.spaces[{index}]"
        if not isinstance(row, dict):
            raise InputError("Each space must be an object.", path)
        normalized = {
            "id": str(row.get("id", f"row-{index + 1}")),
            "name": row.get("name"),
            "building": row.get("building"),
            "date": row.get("date"),
            "available_start": clock(row.get("available_start"), f"{path}.available_start"),
            "available_end": clock(row.get("available_end"), f"{path}.available_end"),
            "capacity": nonnegative_int(row.get("capacity"), f"{path}.capacity"),
            "equipment": string_list(row.get("equipment"), f"{path}.equipment"),
            "equipment_supplied": "equipment" in row,
            "available": row.get("available"),
            "snapshot_row": index,
        }
        missing: list[str] = []
        mismatch = False
        if normalized["available"] is not True:
            if normalized["available"] is None:
                missing.append("available")
            else:
                mismatch = True
        if wanted_date is not None:
            if normalized["date"] is None:
                missing.append("date")
            elif normalized["date"] != wanted_date:
                mismatch = True
        if wanted_building:
            if not normalized["building"]:
                missing.append("building")
            elif wanted_building not in str(normalized["building"]).casefold():
                mismatch = True
        if q_start is not None:
            if normalized["available_start"] is None or normalized["available_end"] is None:
                missing.append("available_interval")
            elif not (
                normalized["available_start"] <= q_start
                and q_end <= normalized["available_end"]
            ):
                mismatch = True
        if minimum is not None:
            if normalized["capacity"] is None:
                missing.append("capacity")
            elif normalized["capacity"] < minimum:
                mismatch = True
        if required:
            if not normalized["equipment_supplied"]:
                missing.append("equipment")
            elif not required.issubset(set(normalized["equipment"])):
                mismatch = True
        if missing and not mismatch:
            unknowns.append({"id": normalized["id"], "missing_for_query": sorted(set(missing))})
        elif not mismatch:
            normalized.pop("equipment_supplied")
            normalized["available_start"] = (
                f"{normalized['available_start'] // 60:02d}:{normalized['available_start'] % 60:02d}"
                if normalized["available_start"] is not None
                else None
            )
            normalized["available_end"] = (
                f"{normalized['available_end'] // 60:02d}:{normalized['available_end'] % 60:02d}"
                if normalized["available_end"] is not None
                else None
            )
            matches.append(normalized)
    matches.sort(
        key=lambda row: (
            row["capacity"] is None,
            row["capacity"] if row["capacity"] is not None else 10**9,
            str(row["building"] or ""),
            str(row["name"] or ""),
        )
    )
    return {
        "schema": "yonsei-space-search/v1",
        "source_scope": "user-supplied-snapshot",
        "live_availability": False,
        "input_count": len(payload["spaces"]),
        "matched_count": len(matches),
        "spaces": matches,
        "excluded_unknown": unknowns,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = run(json.loads(args.input.read_text(encoding="utf-8")))
        print(json.dumps(output, ensure_ascii=False, indent=2))
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
