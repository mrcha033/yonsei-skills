#!/usr/bin/env python3
"""Classify a user-supplied Yonsei page snapshot without reading credentials."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LOGIN_MARKERS = (
    "portal login",
    "external login",
    "로그인 (login)",
    "로그인(login)",
    "세션이 만료",
    "session expired",
    'type="password"',
    "name=\"password\"",
)


def classify(html: str, success_markers: list[str]) -> dict[str, object]:
    lowered = html.lower()
    observed_login = sorted(
        marker for marker in LOGIN_MARKERS if marker.lower() in lowered
    )
    observed_success = sorted(
        marker for marker in success_markers if marker.lower() in lowered
    )
    if observed_login:
        state = "login_required"
    elif observed_success:
        state = "connected"
    else:
        state = "unknown"
    return {
        "schema": "yonsei-browser-session-check/v1",
        "state": state,
        "login_markers": observed_login,
        "success_markers": observed_success,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument(
        "--success-marker",
        action="append",
        default=[],
        help="Visible service-content marker; repeat for alternatives.",
    )
    args = parser.parse_args()
    text = args.html.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\s+", " ", text)
    print(json.dumps(classify(text, args.success_marker), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
