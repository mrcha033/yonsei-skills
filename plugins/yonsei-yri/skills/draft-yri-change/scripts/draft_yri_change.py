#!/usr/bin/env python3
"""Draft an offline YRI achievement modification request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-yri-change-draft/v1"
ERROR_SCHEMA = "yonsei-yri-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password", "passwd", "userpw", "otp", "token", "access_token",
    "refresh_token", "cookie", "cookies", "session", "sessionid",
}
ACTION_KEYS = {"submit", "send", "save", "delete", "approve", "execute"}
MUTABLE_FIELDS = {"title", "year", "kri_id", "issn", "doi", "note"}
TYPE_ALIASES = {
    "논문": "article", "article": "article",
    "저역서": "book", "book": "book",
    "전시작품": "exhibition", "exhibition": "exhibition",
    "연구비": "funding", "funding": "funding",
    "지식재산": "intellectual-property",
    "intellectual-property": "intellectual-property",
    "기술이전": "technology-transfer",
    "technology-transfer": "technology-transfer",
    "수상": "award", "award": "award",
    "학술활동": "academic-activity",
    "academic-activity": "academic-activity",
    "보고서": "report", "report": "report",
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "credential-field-not-allowed",
                    "Credential or session fields are not accepted.",
                    f"{path}.{key}",
                )
            if normalized in ACTION_KEYS:
                raise InputError(
                    "execution-directive-not-allowed",
                    "Execution or submission directives are not accepted.",
                    f"{path}.{key}",
                )
            scan_forbidden(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_forbidden(item, f"{path}[{index}]")


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "A non-empty text value is required.", path)
    return value.strip()


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


def validate_field_value(field: str, value: Any, path: str) -> Any:
    if value is None:
        return None
    if field == "year":
        if isinstance(value, bool) or not isinstance(value, int) or not 1000 <= value <= 9999:
            raise InputError("invalid-year", "Year must be a four-digit integer or null.", path)
        return value
    if not isinstance(value, str):
        raise InputError("invalid-field-value", "Field value must be text or null.", path)
    return value.strip()


def normalize_values(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError("invalid-change-values", "Expected an object of field values.", path)
    unknown = sorted(set(value) - MUTABLE_FIELDS)
    if unknown:
        raise InputError(
            "unsupported-change-field",
            "Unsupported change field: " + ", ".join(unknown),
            path,
        )
    return {
        field: validate_field_value(field, value[field], f"{path}.{field}")
        for field in sorted(value)
    }


def transform(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise InputError("invalid-root", "Input must be a JSON object.")
    scan_forbidden(data)
    captured_at = required_text(data.get("captured_at"), "$.captured_at")
    if data.get("owner_scope") != "self":
        raise InputError("scope-not-self", 'owner_scope must be exactly "self".', "$.owner_scope")
    change = data.get("change")
    if not isinstance(change, dict):
        raise InputError("invalid-change", "change must be an object.", "$.change")
    if change.get("requested_action") != "request-modification":
        raise InputError(
            "unsupported-requested-action",
            'requested_action must be exactly "request-modification".',
            "$.change.requested_action",
        )
    record = change.get("record")
    if not isinstance(record, dict):
        raise InputError("invalid-record", "record must be an object.", "$.change.record")
    record_summary = {
        "record_id": required_text(record.get("record_id"), "$.change.record.record_id"),
        "type": normalize_type(record.get("type"), "$.change.record.type"),
        "title": required_text(record.get("title"), "$.change.record.title"),
    }
    before = normalize_values(change.get("before"), "$.change.before")
    after = normalize_values(change.get("after"), "$.change.after")
    if set(before) != set(after):
        raise InputError(
            "change-field-set-mismatch",
            "before and after must contain the same fields.",
            "$.change",
        )
    changes = [
        {"field": field, "before": before[field], "after": after[field]}
        for field in sorted(before)
        if before[field] != after[field]
    ]
    if not changes:
        raise InputError("no-change", "At least one field must change.", "$.change")
    reason = required_text(change.get("reason"), "$.change.reason")
    raw_attachments = change.get("attachments", [])
    if not isinstance(raw_attachments, list):
        raise InputError(
            "invalid-attachments",
            "attachments must be an array of labels.",
            "$.change.attachments",
        )
    attachments = [
        required_text(item, f"$.change.attachments[{index}]")
        for index, item in enumerate(raw_attachments)
    ]
    change_lines = [
        f"- {item['field']}: {json.dumps(item['before'], ensure_ascii=False)}"
        f" -> {json.dumps(item['after'], ensure_ascii=False)}"
        for item in changes
    ]
    draft_text = "\n".join([
        "YRI 업적 수정 요청 초안",
        f"기록: {record_summary['title']} ({record_summary['record_id']})",
        "변경 사항:",
        *change_lines,
        f"사유: {reason}",
    ])
    return {
        "schema": OUTPUT_SCHEMA,
        "provenance": {
            "mode": "user-supplied-snapshot",
            "captured_at": captured_at,
            "owner_scope": "self",
            "live_system_queried": False,
        },
        "requested_action": "request-modification",
        "record": record_summary,
        "changes": changes,
        "reason": reason,
        "attachment_labels": attachments,
        "draft_text": draft_text,
        "draft_only": True,
        "requires_user_review": True,
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
        print(json.dumps({
            "schema": ERROR_SCHEMA,
            "error": {
                "code": getattr(exc, "code", "invalid-input"),
                "message": str(exc),
                "path": getattr(exc, "path", "$"),
            },
            "live_system_queried": False,
            "writes_performed": False,
            "submitted": False,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
