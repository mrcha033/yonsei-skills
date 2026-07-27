#!/usr/bin/env python3
"""Create an unsent draft for one supplied attendance discrepancy."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-attendance-correction-draft/v1"
ERROR_SCHEMA = "yonsei-attendance-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password",
    "passwd",
    "userpw",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "cookies",
    "session",
    "sessionid",
    "attendance_code",
    "beacon",
    "location",
    "latitude",
    "longitude",
}
ACTION_KEYS = {
    "submit",
    "send",
    "auto_submit",
    "auto_send",
    "apply_change",
    "confirm_and_send",
}
STATUS_ALIASES = {
    "출석": "present",
    "present": "present",
    "o": "present",
    "○": "present",
    "지각": "late",
    "late": "late",
    "결석": "absent",
    "absent": "absent",
    "x": "absent",
    "×": "absent",
    "조퇴": "early-leave",
    "early-leave": "early-leave",
    "early_leave": "early-leave",
    "공결": "excused",
    "유고결석": "excused",
    "인정": "excused",
    "excused": "excused",
    "미처리": "pending",
    "미확정": "pending",
    "pending": "pending",
}
STATUS_KO = {
    "present": "출석",
    "late": "지각",
    "absent": "결석",
    "early-leave": "조퇴",
    "excused": "공결/인정",
    "pending": "미처리",
}
KEYS = {
    "course_code": ("course_code", "courseCode", "code", "학정번호", "교과목번호"),
    "course_title": ("course_title", "title", "course_name", "교과목명"),
    "class_date": ("class_date", "date", "수업일", "수업일자"),
    "recorded_status": ("recorded_status", "status", "출결상태", "기록상태"),
    "requested_status": ("requested_status", "expected_status", "요청상태", "기대상태"),
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_input(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "credential-or-presence-field-not-allowed",
                    "Credential, session, location, beacon, and check-in fields are not accepted.",
                    f"{path}.{key}",
                )
            if normalized in ACTION_KEYS and item not in (False, None, "", 0):
                raise InputError(
                    "submission-not-supported",
                    "This skill creates a draft only and cannot send or apply it.",
                    f"{path}.{key}",
                )
            scan_input(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_input(item, f"{path}[{index}]")


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "A non-empty text value is required.", path)
    return value.strip()


def optional_text(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise InputError("invalid-text", "Expected text.", path)
    return value.strip() or None


def first(row: dict[str, Any], field: str) -> Any:
    for key in KEYS[field]:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def normalize_date(value: Any, path: str) -> str:
    text = required_text(value, path)
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise InputError("invalid-date", "Use an ISO date such as 2026-03-05.", path) from error


def normalize_status(value: Any, path: str) -> str:
    displayed = required_text(value, path)
    key = displayed.lower().replace("_", "-")
    if key not in STATUS_ALIASES:
        raise InputError(
            "unknown-attendance-status",
            "Attendance status is not recognized.",
            path,
        )
    return STATUS_ALIASES[key]


def evidence_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InputError("invalid-evidence", "Evidence must be an array of descriptions.", path)
    return [required_text(item, f"{path}[{index}]") for index, item in enumerate(value)]


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("invalid-input", "Input must be a JSON object.")
    scan_input(payload)
    captured_at = required_text(payload.get("captured_at"), "$.captured_at")
    correction = payload.get("correction")
    if not isinstance(correction, dict):
        raise InputError(
            "invalid-correction",
            "Input must contain a correction object.",
            "$.correction",
        )
    code = required_text(
        first(correction, "course_code"), "$.correction.course_code"
    ).upper()
    title = required_text(
        first(correction, "course_title"), "$.correction.course_title"
    )
    class_date = normalize_date(
        first(correction, "class_date"), "$.correction.class_date"
    )
    recorded = normalize_status(
        first(correction, "recorded_status"), "$.correction.recorded_status"
    )
    requested = normalize_status(
        first(correction, "requested_status"), "$.correction.requested_status"
    )
    if recorded == requested:
        raise InputError(
            "status-not-changed",
            "Recorded and requested statuses must differ.",
            "$.correction.requested_status",
        )
    reason = required_text(correction.get("reason"), "$.correction.reason")
    evidence = evidence_list(correction.get("evidence"), "$.correction.evidence")
    recipient = optional_text(correction.get("recipient"), "$.correction.recipient")
    normalized = {
        "course_code": code,
        "course_title": title,
        "class_date": class_date,
        "recorded_status": recorded,
        "requested_status": requested,
        "reason": reason,
        "evidence": evidence,
        "recipient": recipient,
    }
    digest = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    evidence_lines = (
        "\n".join(f"- {item}" for item in evidence)
        if evidence
        else "- 첨부 또는 설명할 증빙을 확인해 주세요."
    )
    recipient_line = recipient or "담당 교강사/공식 출결변경 접수처 확인 필요"
    message = (
        f"제목: [출결 정정 요청] {title} ({code}) {class_date}\n"
        f"수신: {recipient_line}\n\n"
        "안녕하세요.\n"
        f"{class_date} {title} ({code}) 수업의 출결 기록 확인을 요청드립니다.\n"
        f"- 현재 표시 상태: {STATUS_KO[recorded]}\n"
        f"- 요청 상태: {STATUS_KO[requested]}\n"
        f"- 사유: {reason}\n"
        f"- 증빙:\n{evidence_lines}\n\n"
        "확인 후 정정 가능 여부를 안내해 주시면 감사하겠습니다.\n"
        "[이 문안은 전송되지 않은 검토용 초안입니다.]"
    )
    missing_items = []
    if not recipient:
        missing_items.append("official-recipient-or-submission-path")
    if not evidence:
        missing_items.append("evidence-description")
    return {
        "schema": OUTPUT_SCHEMA,
        "ok": True,
        "draft_id": digest,
        "draft": {**normalized, "message": message},
        "evidence_checklist": [
            {"description": item, "present": True} for item in evidence
        ],
        "missing_items": missing_items,
        "ready_for_user_review": not missing_items,
        "draft_only": True,
        "submitted": False,
        "actions": {
            "checkin_performed": False,
            "official_record_changed": False,
            "external_message_sent": False,
        },
        "provenance": {
            "mode": "user-supplied-snapshot",
            "captured_at": captured_at,
            "live_system_queried": False,
        },
    }


def load_input(path: str) -> Any:
    try:
        if path == "-":
            return json.load(sys.stdin, parse_constant=reject_json_constant)
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=reject_json_constant,
        )
    except InputError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise InputError("invalid-json", "Could not read JSON input.") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="JSON file, or - for stdin")
    args = parser.parse_args()
    try:
        output = run(load_input(args.input))
        exit_code = 0
    except InputError as error:
        output = {
            "schema": ERROR_SCHEMA,
            "ok": False,
            "error": {"code": error.code, "message": str(error), "path": error.path},
        }
        exit_code = 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
