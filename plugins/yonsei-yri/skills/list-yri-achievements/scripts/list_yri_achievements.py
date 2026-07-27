#!/usr/bin/env python3
"""Normalize a user-supplied, self-owned YRI achievement snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-yri-achievement-list/v1"
ERROR_SCHEMA = "yonsei-yri-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password", "passwd", "userpw", "otp", "token", "access_token",
    "refresh_token", "cookie", "cookies", "session", "sessionid",
}
TYPE_ALIASES = {
    "논문": "article",
    "article": "article",
    "저역서": "book",
    "book": "book",
    "전시작품": "exhibition",
    "exhibition": "exhibition",
    "연구비": "funding",
    "funding": "funding",
    "지식재산": "intellectual-property",
    "intellectual-property": "intellectual-property",
    "기술이전": "technology-transfer",
    "technology-transfer": "technology-transfer",
    "수상": "award",
    "award": "award",
    "학술활동": "academic-activity",
    "academic-activity": "academic-activity",
    "보고서": "report",
    "report": "report",
}
SOURCE_FORMATS = {"json", "excel-transcribed"}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_credentials(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "credential-field-not-allowed",
                    "Credential or session fields are not accepted.",
                    f"{path}.{key}",
                )
            scan_credentials(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_credentials(item, f"{path}[{index}]")


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


def normalize_type(value: Any, path: str) -> str:
    raw = required_text(value, path)
    key = raw.lower() if raw.isascii() else raw
    if key not in TYPE_ALIASES:
        raise InputError(
            "unknown-achievement-type",
            "Achievement type is outside the declared YRI type contract.",
            path,
        )
    return TYPE_ALIASES[key]


def normalize_year(value: Any, path: str) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1000 <= value <= 9999:
        raise InputError("invalid-year", "Year must be a four-digit integer.", path)
    return value


def transform(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise InputError("invalid-root", "Input must be a JSON object.")
    scan_credentials(data)
    captured_at = required_text(data.get("captured_at"), "$.captured_at")
    if data.get("owner_scope") != "self":
        raise InputError(
            "scope-not-self",
            'owner_scope must be exactly "self".',
            "$.owner_scope",
        )
    source_format = data.get("source_format", "json")
    if source_format not in SOURCE_FORMATS:
        raise InputError(
            "unsupported-source-format",
            "source_format must be json or excel-transcribed.",
            "$.source_format",
        )
    raw_rows = data.get("achievements")
    if not isinstance(raw_rows, list):
        raise InputError("invalid-achievements", "achievements must be an array.", "$.achievements")

    records = []
    warnings = []
    type_counts = {value: 0 for value in sorted(set(TYPE_ALIASES.values()))}
    approval_counts = {}
    seen_record_ids = set()
    for index, raw in enumerate(raw_rows):
        path = f"$.achievements[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-achievement", "Each achievement must be an object.", path)
        achievement_type = normalize_type(raw.get("type"), f"{path}.type")
        title = required_text(raw.get("title"), f"{path}.title")
        approval_status = required_text(
            raw.get("approval_status"), f"{path}.approval_status"
        )
        record_id = optional_text(raw.get("record_id"), f"{path}.record_id")
        if record_id is not None:
            if record_id in seen_record_ids:
                raise InputError(
                    "duplicate-record-id",
                    "record_id must be unique within the snapshot.",
                    f"{path}.record_id",
                )
            seen_record_ids.add(record_id)
        record = {
            "record_id": record_id,
            "type": achievement_type,
            "title": title,
            "year": normalize_year(raw.get("year"), f"{path}.year"),
            "approval_status": approval_status,
            "kri_id": optional_text(raw.get("kri_id"), f"{path}.kri_id"),
            "issn": optional_text(raw.get("issn"), f"{path}.issn"),
            "doi": optional_text(raw.get("doi"), f"{path}.doi"),
        }
        if record["year"] is None:
            warnings.append({"code": "missing-year", "record_index": index})
        if achievement_type == "article" and not (
            record["kri_id"] or record["issn"] or record["doi"]
        ):
            warnings.append(
                {"code": "article-without-kri-issn-or-doi", "record_index": index}
            )
        records.append(record)
        type_counts[achievement_type] += 1
        approval_counts[approval_status] = approval_counts.get(approval_status, 0) + 1

    records.sort(
        key=lambda row: (
            row["type"],
            -(row["year"] or 0),
            row["title"].casefold(),
            row["record_id"] or "",
        )
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "provenance": {
            "mode": "user-supplied-snapshot",
            "source_format": source_format,
            "captured_at": captured_at,
            "owner_scope": "self",
            "live_system_queried": False,
        },
        "records": records,
        "summary": {
            "record_count": len(records),
            "counts_by_type": {
                key: count for key, count in type_counts.items() if count
            },
            "counts_by_approval_status": dict(sorted(approval_counts.items())),
        },
        "warnings": warnings,
        "complete": not warnings,
        "writes_performed": False,
        "submitted": False,
    }


def load_input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_constant=reject_json_constant)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="JSON path or - for stdin")
    args = parser.parse_args()
    try:
        result = transform(load_input(args.input))
    except (InputError, json.JSONDecodeError, OSError) as exc:
        error = {
            "schema": ERROR_SCHEMA,
            "error": {
                "code": getattr(exc, "code", "invalid-input"),
                "message": str(exc),
                "path": getattr(exc, "path", "$"),
            },
            "live_system_queried": False,
            "writes_performed": False,
            "submitted": False,
        }
        print(json.dumps(error, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
