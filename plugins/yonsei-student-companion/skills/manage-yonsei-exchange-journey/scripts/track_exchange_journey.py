#!/usr/bin/env python3
"""Summarize the next step in a Yonsei exchange journey."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


STAGES = (
    "eligibility",
    "yonsei_application",
    "nomination",
    "host_application",
    "documents",
    "departure",
    "study_abroad",
    "credit_recognition",
    "return",
    "final_report",
)
DONE = {"completed", "approved", "accepted", "done", "완료", "승인"}


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("stages"), list):
        raise ValueError("Expected an object with a stages array.")
    by_name: dict[str, dict[str, Any]] = {}
    for raw in payload["stages"]:
        if not isinstance(raw, dict) or raw.get("stage") not in STAGES:
            raise ValueError(f"Each stage must be one of {list(STAGES)}.")
        stage = str(raw["stage"])
        by_name[stage] = {
            "stage": stage,
            "status": raw.get("status", "not_started"),
            "deadline": raw.get("deadline"),
            "owner": raw.get("owner"),
            "missing_documents": raw.get("missing_documents", []),
            "source": raw.get("source"),
        }
    current = None
    for stage in STAGES:
        item = by_name.get(stage)
        if item and str(item["status"]).strip().casefold() not in DONE:
            current = item
            break
    return {
        "schema": "yonsei-exchange-journey/v1",
        "route": payload.get("route"),
        "current_stage": current,
        "next_deadline": current.get("deadline") if current else None,
        "completed_stages": [
            stage
            for stage in STAGES
            if stage in by_name and str(by_name[stage]["status"]).strip().casefold() in DONE
        ],
        "later_stages": [by_name[stage] for stage in STAGES if stage in by_name and by_name[stage] is not current],
        "action_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
        output, code = run(payload), 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        output, code = {"schema": "yonsei-exchange-journey-error/v1", "error": str(exc)}, 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
