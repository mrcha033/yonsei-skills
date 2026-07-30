#!/usr/bin/env python3
"""Prepare an official route for a Yonsei student-activity document."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROUTES = {
    "student_activity": "Underwood student activity record",
    "ambassador": "responsible student-activity office",
    "resident_assistant": "responsible dorm office",
    "education_practicum": "Underwood teaching profession or practicum menu",
    "tuition_payment": "Underwood tuition and payment certificate menu",
    "dorm": "official dorm office or dorm system",
}


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object.")
    document_type = str(payload.get("document_type", "")).strip().casefold()
    if document_type not in ROUTES:
        raise ValueError(f"document_type must be one of {sorted(ROUTES)}.")
    required = ("language", "purpose", "output_format")
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    return {
        "schema": "yonsei-student-document/v1",
        "document_type": document_type,
        "official_route": ROUTES[document_type],
        "language": payload.get("language"),
        "purpose": payload.get("purpose"),
        "recipient": payload.get("recipient"),
        "output_format": payload.get("output_format"),
        "fee": payload.get("fee"),
        "missing_fields": missing,
        "ready_for_confirmation": not missing,
        "issuance_performed": False,
        "font_check_required": str(payload.get("output_format", "")).casefold() == "pdf",
        "next_step": "collect-missing-fields" if missing else "review-official-issuance-screen",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
        output, code = run(payload), 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        output, code = {"schema": "yonsei-student-document-error/v1", "error": str(exc)}, 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
