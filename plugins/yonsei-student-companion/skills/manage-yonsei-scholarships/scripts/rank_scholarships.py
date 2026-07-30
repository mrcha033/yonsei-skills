#!/usr/bin/env python3
"""Rank official Yonsei scholarship opportunities conservatively."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def run(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("scholarships"), list):
        raise ValueError("Expected an object with a scholarships array.")
    now = datetime.fromisoformat(str(payload.get("now", datetime.now().astimezone().isoformat())).replace("Z", "+00:00"))
    ranked: list[dict[str, Any]] = []
    for raw in payload["scholarships"]:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            raise ValueError("Each scholarship requires a name.")
        deadline = datetime.fromisoformat(str(raw["deadline"]).replace("Z", "+00:00")) if raw.get("deadline") else None
        if deadline and deadline < now:
            continue
        missing = [str(item).strip() for item in raw.get("missing_documents", []) if str(item).strip()]
        eligible = raw.get("eligible")
        days = (deadline - now).total_seconds() / 86400 if deadline else 9999
        score = (100 if eligible is True else 20 if eligible is None else -100) - min(days, 90) - 8 * len(missing)
        ranked.append(
            {
                "name": str(raw["name"]).strip(),
                "eligible": eligible,
                "deadline": deadline.isoformat() if deadline else None,
                "benefit": raw.get("benefit", raw.get("amount")),
                "required_documents": raw.get("required_documents", []),
                "missing_documents": missing,
                "application_status": raw.get("application_status"),
                "source": raw.get("source"),
                "priority_score": round(score, 2),
                "next_action": (
                    "confirm-eligibility"
                    if eligible is None
                    else "not-eligible"
                    if eligible is False
                    else "prepare-missing-documents"
                    if missing
                    else "review-official-application"
                ),
            }
        )
    ranked.sort(key=lambda item: (-item["priority_score"], item["deadline"] or "9999", item["name"]))
    return {
        "schema": "yonsei-scholarship-ranking/v1",
        "opportunities": ranked,
        "application_performed": False,
        "eligibility_guaranteed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
        output, code = run(payload), 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        output, code = {"schema": "yonsei-scholarship-error/v1", "error": str(exc)}, 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
