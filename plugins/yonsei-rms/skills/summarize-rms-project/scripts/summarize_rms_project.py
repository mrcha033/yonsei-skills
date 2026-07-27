#!/usr/bin/env python3
"""Summarize a user-supplied RMS project snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-rms-project-summary/v1"
ERROR_SCHEMA = "yonsei-rms-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password", "passwd", "userpw", "otp", "token", "access_token",
    "refresh_token", "cookie", "cookies", "session", "sessionid",
    "name", "full_name", "display_name", "email", "phone", "phone_number",
    "student_id", "employee_id", "researcher_id",
    "resident_registration_number", "rrn", "bank_account", "account_number",
    "tax_id",
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


def optional_text(value: Any, path: str) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise InputError("invalid-text", "Expected text or null.", path)
    return value.strip() or None


def parse_date(value: Any, path: str) -> date:
    text = required_text(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise InputError("invalid-date", "Use an ISO date in YYYY-MM-DD form.", path) from exc


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


def transform(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise InputError("invalid-root", "Input must be a JSON object.")
    scan_sensitive(data)
    captured_at = required_text(data.get("captured_at"), "$.captured_at")
    source_format = data.get("source_format", "json")
    if source_format not in {"json", "excel-transcribed"}:
        raise InputError(
            "unsupported-source-format",
            "source_format must be json or excel-transcribed.",
            "$.source_format",
        )
    project = data.get("project")
    if not isinstance(project, dict):
        raise InputError("invalid-project", "project must be an object.", "$.project")
    identity = {
        "project_code": required_text(project.get("project_code"), "$.project.project_code"),
        "title": required_text(project.get("title"), "$.project.title"),
        "status": required_text(project.get("status"), "$.project.status"),
    }
    period = project.get("period")
    if not isinstance(period, dict):
        raise InputError("invalid-period", "period must be an object.", "$.project.period")
    start = parse_date(period.get("start_date"), "$.project.period.start_date")
    end = parse_date(period.get("end_date"), "$.project.period.end_date")
    if end < start:
        raise InputError(
            "invalid-project-period",
            "Project end_date must not be before start_date.",
            "$.project.period",
        )

    budget = project.get("budget")
    if not isinstance(budget, dict):
        raise InputError("invalid-budget", "budget must be an object.", "$.project.budget")
    currency = required_text(budget.get("currency"), "$.project.budget.currency")
    total = decimal_value(budget.get("total"), "$.project.budget.total")
    executed = decimal_value(budget.get("executed"), "$.project.budget.executed")
    committed = decimal_value(budget.get("committed", 0), "$.project.budget.committed")
    calculated_remaining = total - executed - committed
    issues = []
    if calculated_remaining < 0:
        issues.append({
            "code": "budget-overcommitted",
            "amount": amount_text(-calculated_remaining),
        })
    supplied_remaining = None
    if "remaining" in budget:
        supplied_remaining = decimal_value(budget["remaining"], "$.project.budget.remaining")
        if supplied_remaining != calculated_remaining:
            issues.append({
                "code": "remaining-mismatch",
                "supplied": amount_text(supplied_remaining),
                "calculated": amount_text(calculated_remaining),
            })

    workflow = project.get("workflow")
    if not isinstance(workflow, dict):
        raise InputError("invalid-workflow", "workflow must be an object.", "$.project.workflow")
    workflow_summary = {
        "stage": required_text(workflow.get("stage"), "$.project.workflow.stage"),
        "pending_action": optional_text(
            workflow.get("pending_action"), "$.project.workflow.pending_action"
        ),
    }

    raw_participants = project.get("participants")
    if not isinstance(raw_participants, list):
        raise InputError(
            "invalid-participants",
            "participants must be an array.",
            "$.project.participants",
        )
    seen_keys = set()
    counts_by_role = {}
    counts_by_status = {}
    for index, participant in enumerate(raw_participants):
        path = f"$.project.participants[{index}]"
        if not isinstance(participant, dict):
            raise InputError("invalid-participant", "Each participant must be an object.", path)
        key = required_text(participant.get("participant_key"), f"{path}.participant_key")
        if key in seen_keys:
            issues.append({"code": "duplicate-participant-key", "participant_index": index})
        seen_keys.add(key)
        role = required_text(participant.get("role"), f"{path}.role")
        status = optional_text(participant.get("status"), f"{path}.status")
        counts_by_role[role] = counts_by_role.get(role, 0) + 1
        if status:
            counts_by_status[status] = counts_by_status.get(status, 0) + 1

    return {
        "schema": OUTPUT_SCHEMA,
        "provenance": {
            "mode": "user-supplied-snapshot",
            "source_format": source_format,
            "captured_at": captured_at,
            "live_system_queried": False,
        },
        "project": identity,
        "period": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "calendar_days_inclusive": (end - start).days + 1,
        },
        "budget": {
            "currency": currency,
            "total": amount_text(total),
            "executed": amount_text(executed),
            "committed": amount_text(committed),
            "calculated_remaining": amount_text(calculated_remaining),
            "supplied_remaining": (
                amount_text(supplied_remaining) if supplied_remaining is not None else None
            ),
        },
        "participants": {
            "count": len(raw_participants),
            "counts_by_role": dict(sorted(counts_by_role.items())),
            "counts_by_status": dict(sorted(counts_by_status.items())),
        },
        "workflow": workflow_summary,
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
