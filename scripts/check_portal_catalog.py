#!/usr/bin/env python3
"""Compare packaged Yonsei portal targets with the current official mapping."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "packages" / "yonsei-service-runtime" / "services.json"
ENDPOINT = "https://portal.yonsei.ac.kr/portal/MainCtr/findLinkInfo.do"


def normalized(url: str) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    url = url.replace("{locale}", "ko")
    parts = urllib.parse.urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    query = tuple(sorted(urllib.parse.parse_qsl(parts.query, keep_blank_values=True)))
    return parts.hostname or "", path, query


def main() -> int:
    request = urllib.request.Request(
        ENDPOINT,
        data=b"",
        headers={
            "User-Agent": "yonsei-skills-catalog-check/0.1",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        outer = json.load(response)
    official = json.loads(outer["linkInfo"])
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    problems: list[str] = []
    checked = 0
    for service_id, service in catalog["services"].items():
        portal_key = service.get("portal_key")
        if not portal_key:
            continue
        checked += 1
        if portal_key not in official:
            problems.append(f"{service_id}: missing portal key {portal_key}")
            continue
        packaged_url = (
            service.get("portal_catalog_url")
            or service.get("portal_url")
            or service.get("direct_url")
            or service["entry_url"]
        )
        current_url = official[portal_key]["address"]
        if normalized(packaged_url) != normalized(current_url):
            problems.append(
                f"{service_id}: packaged {packaged_url!r} != portal {current_url!r}"
            )
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        return 1
    print(f"Portal catalog check: PASS ({checked} mapped services)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
