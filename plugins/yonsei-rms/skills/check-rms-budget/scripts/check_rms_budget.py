#!/usr/bin/env python3
"""Check arithmetic in a user-supplied RMS budget snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-rms-budget-check/v1"
ERROR_SCHEMA = "yonsei-rms-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password", "passwd", "userpw", "otp", "token", "access_token",
    "refresh_token", "cookie", "cookies", "session", "sessionid",
    "resident_registration_number", "rrn", "bank_account", "account_number",
    "tax_id", "card_number",
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_sensitive(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "sensitive-field-not-allowed",
                    "Credential, session, or high-risk identifier fields are not accepted.",
                    f"{path}.{key}",
                )
            scan_sensitive(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_sensitive(item, f"{path}[{index}]")


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "A non-empty text value is required.", path)
    return value.strip()


def decimal_value(value: Any, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise InputError("invalid-amount", "Amount must be a number or decimal string.", path)
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise InputError("invalid-amount", "Amount is not a finite decimal.", path) from exc
    if not amount.is_finite() or amount < 0:
        raise InputError("invalid-amount", "Amount must be finite and non-negative.", path)
    return amount


def amount_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def read_totals(raw: Any, path: str, require: bool) -> dict[str, Decimal]:
    if raw is None and not require:
        return {}
    if not isinstance(raw, dict):
        raise InputError("invalid-totals", "Expected an object of totals.", path)
    allowed = {"allocated", "executed", "committed", "remaining"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise InputError(
            "unsupported-total-field",
            "Unsupported total field: " + ", ".join(unknown),
            path,
        )
    if require:
        for field in ("allocated", "executed"):
            if field not in raw:
                raise InputError("missing-total", f"{field} is required.", f"{path}.{field}")
    return {
        field: decimal_value(value, f"{path}.{field}")
        for field, value in raw.items()
    }


def transform(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise InputError("invalid-root", "Input must be a JSON object.")
    scan_sensitive(data)
    captured_at = required_text(data.get("captured_at"), "$.captured_at")
    project_code = required_text(data.get("project_code"), "$.project_code")
    currency = required_text(data.get("currency"), "$.currency")
    source_format = data.get("source_format", "json")
    if source_format not in {"json", "excel-transcribed"}:
        raise InputError(
            "unsupported-source-format",
            "source_format must be json or excel-transcribed.",
            "$.source_format",
        )
    raw_lines = data.get("budget_lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise InputError(
            "invalid-budget-lines",
            "budget_lines must be a non-empty array.",
            "$.budget_lines",
        )

    totals = {
        "allocated": Decimal(0),
        "executed": Decimal(0),
        "committed": Decimal(0),
    }
    seen_categories = set()
    lines = []
    issues = []
    for index, raw in enumerate(raw_lines):
        path = f"$.budget_lines[{index}]"
        if not isinstance(raw, dict):
            raise InputError("invalid-budget-line", "Each budget line must be an object.", path)
        category = required_text(raw.get("category"), f"{path}.category")
        category_key = category.casefold()
        if category_key in seen_categories:
            raise InputError(
                "duplicate-category",
                "Each category must be unique in this snapshot contract.",
                f"{path}.category",
            )
        seen_categories.add(category_key)
        allocated = decimal_value(raw.get("allocated"), f"{path}.allocated")
        executed = decimal_value(raw.get("executed"), f"{path}.executed")
        committed = decimal_value(raw.get("committed", 0), f"{path}.committed")
        remaining = allocated - executed - committed
        totals["allocated"] += allocated
        totals["executed"] += executed
        totals["committed"] += committed
        if remaining < 0:
            issues.append({
                "code": "line-overcommitted",
                "line_index": index,
                "category": category,
                "amount": amount_text(-remaining),
            })
        lines.append({
            "category": category,
            "allocated": amount_text(allocated),
            "executed": amount_text(executed),
            "committed": amount_text(committed),
            "calculated_remaining": amount_text(remaining),
        })

    calculated_remaining = (
        totals["allocated"] - totals["executed"] - totals["committed"]
    )
    calculated = dict(totals)
    calculated["remaining"] = calculated_remaining
    supplied = read_totals(data.get("supplied_totals"), "$.supplied_totals", False)
    for field, supplied_value in sorted(supplied.items()):
        if supplied_value != calculated[field]:
            issues.append({
                "code": "supplied-total-mismatch",
                "field": field,
                "supplied": amount_text(supplied_value),
                "calculated": amount_text(calculated[field]),
            })

    return {
        "schema": OUTPUT_SCHEMA,
        "provenance": {
            "mode": "user-supplied-snapshot",
            "source_format": source_format,
            "captured_at": captured_at,
            "live_system_queried": False,
        },
        "project_code": project_code,
        "currency": currency,
        "lines": lines,
        "calculated_totals": {
            field: amount_text(calculated[field])
            for field in ("allocated", "executed", "committed", "remaining")
        },
        "supplied_totals": {
            field: amount_text(value) for field, value in sorted(supplied.items())
        } if supplied else None,
        "issues": issues,
        "complete": not issues,
        "writes_performed": False,
        "submitted": False,
    }


def load_input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_float=Decimal, parse_constant=reject_json_constant)


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
