#!/usr/bin/env python3
"""Describe the supported browser path for Yonsei shuttle booking."""

from __future__ import annotations

import argparse
import json
import platform


SERVICE_URL = (
    "https://underwood1.yonsei.ac.kr/com/lgin/"
    "SsoCtr/initExtPageWork.do?link=shuttle"
)
ALIASES = {
    "darwin": "macos",
    "mac": "macos",
    "macos": "macos",
    "linux": "linux",
    "windows": "windows",
    "win32": "windows",
}


def capabilities(system: str | None = None) -> dict[str, object]:
    raw = system or platform.system()
    normalized = ALIASES.get(raw.strip().casefold(), "unsupported")
    supported = normalized in {"windows", "macos", "linux"}
    return {
        "schema": "yonsei-browser-platform/v1",
        "service": "shuttle",
        "platform": normalized,
        "supported": supported,
        "service_url": SERVICE_URL,
        "execution": (
            "persistent-desktop-browser"
            if supported
            else "review-only-browser-handoff"
        ),
        "login": "reuse-official-browser-profile",
        "student_cli_required": False,
        "final_action": "confirm-once-then-verify-official-history",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", help="Override platform detection for checks.")
    args = parser.parse_args()
    result = capabilities(args.platform)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["supported"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
